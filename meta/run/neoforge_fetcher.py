import logging
import asyncio
from typing import Optional
from datetime import datetime, timezone

from meta.run.base_fetcher import BaseFetcher
from meta.models.neoforge_model import (
    MavenMetadata,
    NeoForgeRawBuild,
    NeoForgeMetaBuild,
    NeoForgeMetaVersionFile,
    NeoForgeMetaVersionEntry,
    NeoForgeMetaVersion
)

URL = "https://maven.neoforged.net/releases/net/neoforged/neoforge"

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

class NeoForgeFetcher(BaseFetcher):
    platform_id = "neoforge"
    platform_name = "NeoForge"
    platform_uid = "net.neoforged"

    async def fetch(self) -> Optional[tuple[NeoForgeMetaVersion, dict[str, NeoForgeMetaVersionFile]]]:
        logger.info("[NeoForge] Fetching NeoForge versions...")

        xml_text = await self.get(f"{URL}/maven-metadata.xml")
        if not xml_text:
            logger.error("[NeoForge] Failed to fetch maven-metadata.xml")
            return None

        metadata = MavenMetadata.from_xml(xml_text.encode())
        versions = metadata.all_versions()
        logger.info(f"[NeoForge] Loaded {len(versions)} versions")

        semaphore = asyncio.Semaphore(15)

        async def fetch_one(version: str):
            async with semaphore:
                logger.debug(f"[NeoForge] Fetching build for {version}")
                return await self._fetch_raw_build(version)
        
        tasks = await asyncio.gather(*[fetch_one(v) for v in versions])
        raw_builds = [b for b in tasks if b is not None]
        logger.info(f"[NeoForge] Fetched {len(raw_builds)} builds")

        version_files: dict[str, NeoForgeMetaVersionFile] = {}
        version_entries: list[NeoForgeMetaVersionEntry] = []
        recommended: list[str] = []

        for raw_build in reversed(raw_builds):
            mc_version = raw_build.mc_version
            version_file = NeoForgeMetaVersionFile.from_raw(raw=raw_build, uid=self.platform_uid)

            if mc_version not in version_files:
                version_files[mc_version] = version_file
            else:
                version_files[mc_version].builds.extend(version_file.builds)

            if mc_version not in [e.mc_version for e in version_entries]:
                version_entries.append(NeoForgeMetaVersionEntry(
                    mcVersion=mc_version,
                    sha256="",
                    url=f"{self.platform_uid}/{raw_build.version}.json"
                ))
            
            if raw_build.recommended and mc_version not in recommended:
                recommended.append(mc_version)
            
        logger.info(f"[NeoForge] Processed {len(version_entries)} MC versions")

        version_entries.reverse()

        package = NeoForgeMetaVersion(
            uid=self.platform_uid,
            name=self.platform_name,
            recommended=recommended,
            versions=version_entries,
        )

        return package, version_files

    async def _fetch_raw_build(self, version: str) -> Optional[NeoForgeRawBuild]:
        sha1_url = f"{URL}/{version}/neoforge-{version}-installer.jar.sha1"
        logger.info(f"[NeoForge] Fetching SHA1: {sha1_url}")
        sha1, release_time = await asyncio.gather(
            self.get(sha1_url),
            self._fetch_release_time(version)
        )

        if not sha1:
            logger.warning(f"[NeoForge] Failed to fetch SHA1 for {version}")
            return None

        if not release_time:
            logger.warning(f"[NeoForge] Failed to fetch release time for {version}")
    
        return NeoForgeRawBuild.create(version=version, sha1=sha1.strip(), release_time=release_time)
    
    async def _fetch_release_time(self, version: str) -> Optional[datetime]:
        url = f"https://maven.neoforged.net/api/maven/details/releases/net%2Fneoforged%2Fneoforge/{version}"
        data = await self.get_json(url)
        if not data:
            logger.warning(f"[NeoForge] No data from release time API for {version}")
            return None
    
        logger.debug(f"[NeoForge] Release time API response for {version}: {data}")
    
        for file in data.get("files", []):
            name = file.get("name", "")
            logger.debug(f"[NeoForge] File: {name}")
            if name.endswith("-installer.jar"):
                timestamp = file.get("lastModifiedTime")
                logger.debug(f"[NeoForge] Found installer, timestamp: {timestamp}")
                if timestamp:
                    return datetime.fromtimestamp(timestamp, tz=timezone.utc)
    
        logger.warning(f"[NeoForge] No installer.jar found in files for {version}")
        return None