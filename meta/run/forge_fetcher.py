import logging
import asyncio
from typing import Optional
from email.utils import parsedate_to_datetime

from meta.run.base_fetcher import BaseFetcher
from meta.models.forge_model import (
    ForgePromos,
    ForgeRawBuild,
    ForgeMetaVersionFile,
    ForgeMetaVersionEntry,
    ForgeMetaVersion,
)

MAVEN_BASE = "https://maven.minecraftforge.net/net/minecraftforge/forge"
PROMOS_URL = "https://files.minecraftforge.net/net/minecraftforge/forge/promotions_slim.json"
INDEX_URL = "https://files.minecraftforge.net/net/minecraftforge/forge/maven-metadata.json"

INSTALLER_MIN_MC = (1, 5, 2)

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


def _has_installer(mc_version: str) -> bool:
    try:
        parts = mc_version.split(".")
        major = int(parts[0])
        minor = int(parts[1]) if len(parts) > 1 else 0
        patch = int(parts[2]) if len(parts) > 2 else 0
        return (major, minor, patch) >= INSTALLER_MIN_MC
    except (ValueError, IndexError):
        return False


class ForgeFetcher(BaseFetcher):
    platform_id = "forge"
    platform_name = "Forge"
    platform_uid = "net.minecraftforge"

    async def fetch(self) -> Optional[tuple[ForgeMetaVersion, dict[str, ForgeMetaVersionFile]]]:
        logger.info("[Forge] Fetching Forge versions...")

        index_raw, promos_raw = await asyncio.gather(
            self.get_json(INDEX_URL),
            self.get_json(PROMOS_URL),
        )

        if not index_raw or not promos_raw:
            logger.error("[Forge] Failed to fetch index or promos")
            return None

        promos = ForgePromos(**promos_raw)
        index: dict[str, list[str]] = index_raw

        total = sum(len(v) for mc, v in index.items() if _has_installer(mc))
        logger.info(f"[Forge] Loaded {total} builds with installer across {len(index)} MC versions")

        semaphore = asyncio.Semaphore(10)

        async def fetch_one(long_version: str, recommended: bool):
            async with semaphore:
                return await self._fetch_raw_build(long_version, recommended)

        tasks = []
        for mc_version, long_versions in index.items():
            if not _has_installer(mc_version):
                logger.debug(f"[Forge] Skipping {mc_version} (no installer)")
                continue
            recommended_forge = promos.get_recommended(mc_version)
            for long_version in long_versions:
                forge_version = long_version.split("-", 1)[1] if "-" in long_version else ""
                is_recommended = forge_version == recommended_forge
                tasks.append(fetch_one(long_version, is_recommended))

        results = await asyncio.gather(*tasks)
        raw_builds = [b for b in results if b is not None]
        logger.info(f"[Forge] Fetched {len(raw_builds)} builds")

        version_files: dict[str, ForgeMetaVersionFile] = {}
        version_entries: list[ForgeMetaVersionEntry] = []
        recommended: list[str] = []

        for raw in reversed(raw_builds):
            mc_version = raw.mc_version
            version_file = ForgeMetaVersionFile.from_raw(raw=raw, uid=self.platform_uid)

            if mc_version not in version_files:
                version_files[mc_version] = version_file
            else:
                version_files[mc_version].builds.extend(version_file.builds)

            if mc_version not in [e.mc_version for e in version_entries]:
                version_entries.append(ForgeMetaVersionEntry(
                    mcVersion=mc_version,
                    sha256="",
                    url=f"{self.platform_uid}/{mc_version}.json"
                ))

            if raw.recommended and mc_version not in recommended:
                recommended.append(mc_version)

        logger.info(f"[Forge] Processed {len(version_entries)} MC versions")

        package = ForgeMetaVersion(
            uid=self.platform_uid,
            name=self.platform_name,
            recommended=recommended,
            versions=version_entries,
        )

        return package, version_files

    async def _fetch_raw_build(self, long_version: str, recommended: bool = False) -> Optional[ForgeRawBuild]:
        raw = ForgeRawBuild.from_long_version(long_version, recommended=recommended)
        sha1, release_time = await asyncio.gather(
            self.get(raw.sha1_url),
            self._fetch_release_time(long_version),
        )
        if not sha1:
            logger.warning(f"[Forge] Failed to fetch SHA1 for {long_version}")
            return None
        raw.sha1 = sha1.strip()
        raw.release_time = release_time
        return raw

    async def _fetch_release_time(self, long_version: str) -> Optional[str]:
        url = f"{MAVEN_BASE}/{long_version}/forge-{long_version}-installer.jar"
        headers = await self.head(url)
        if not headers:
            return None
        last_modified = headers.get("Last-Modified")
        if last_modified:
            return parsedate_to_datetime(last_modified).isoformat()
        return None