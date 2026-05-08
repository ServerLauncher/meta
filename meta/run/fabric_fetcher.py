import logging
import asyncio
from typing import Optional
from datetime import datetime

from meta.run.base_fetcher import BaseFetcher
from meta.models.fabric_model import (
    FabricGameVersion,
    FabricLoaderEntry,
    FabricInstallerVersion,
    FabricMetaVersionFile,
    FabricMetaVersionEntry,
    FabricMetaVersion
)

URL = "https://meta.fabricmc.net/v2/versions"
MAVEN_URL = "https://maven.fabricmc.net"

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


class FabricFetcher(BaseFetcher):
    platform_id = "fabric"
    platform_name = "Fabric"
    platform_uid = "net.fabricmc.fabric"

    def __init__(self):
        super().__init__()
        self._maven_cache: dict[str, tuple[Optional[str], Optional[str]]] = {}

    async def fetch(self) -> Optional[tuple[FabricMetaVersion, dict[str, FabricMetaVersionFile]]]:
        logger.info("[Fabric] Fetching game versions...")

        raw_versions = await self.get_json(f"{URL}/game")
        if not raw_versions:
            logger.error("[Fabric] Failed to fetch game versions")
            return None

        game_versions = [FabricGameVersion(**v) for v in raw_versions]
        mc_versions = [v.version for v in game_versions]
        logger.info(f"[Fabric] Loaded {len(mc_versions)} MC versions")

        installer_version = await self._fetch_installer_version()
        if not installer_version:
            logger.error("[Fabric] Failed to fetch installer version")
            return None

        logger.info(f"[Fabric] Using installer version: {installer_version}")

        semaphore = asyncio.Semaphore(20)

        async def fetch_one(mc_version: str):
            async with semaphore:
                logger.debug(f"[Fabric] Fetching loaders for {mc_version}")
                return await self._fetch_loaders(mc_version, installer_version)

        logger.info(f"[Fabric] Starting to fetch loaders for {len(mc_versions)} versions...")
        tasks = await asyncio.gather(*[fetch_one(v) for v in mc_versions])
        logger.info(f"[Fabric] Finished fetching all loaders")

        version_files: dict[str, FabricMetaVersionFile] = {}
        version_entries: list[FabricMetaVersionEntry] = []
        recommended: list[str] = []

        for mc_version, version_file in zip(mc_versions, tasks):
            if not version_file:
                logger.debug(f"[Fabric] Skipping {mc_version} (no loaders)")
                continue

            version_files[mc_version] = version_file

            version_entries.append(
                FabricMetaVersionEntry(
                    mcVersion=mc_version,
                    sha256="",
                    url=f"{self.platform_uid}/{mc_version}.json"
                )
            )

            if not recommended:
                recommended.append(mc_version)

        logger.info(f"[Fabric] Processed {len(version_entries)} MC versions")

        package = FabricMetaVersion(
            uid=self.platform_uid,
            name=self.platform_name,
            recommended=recommended,
            versions=version_entries
        )

        return package, version_files

    async def _fetch_loaders(self, mc_version: str, installer_version: str) -> Optional[FabricMetaVersionFile]:
        raw = await self.get_json(f"{URL}/loader/{mc_version}")
        if not raw:
            logger.error(f"[Fabric] Failed to fetch loaders for {mc_version}")
            return None

        loader_entries = [FabricLoaderEntry(**entry) for entry in raw]

        if not loader_entries:
            logger.debug(f"[Fabric] No loaders for {mc_version}")
            return None

        semaphore = asyncio.Semaphore(20)

        async def fetch_metadata(entry: FabricLoaderEntry):
            async with semaphore:
                maven_key = entry.loader.maven
                if maven_key:
                    # Check cache first
                    if maven_key in self._maven_cache:
                        logger.debug(f"[Fabric] Cache hit for {maven_key}")
                        return self._maven_cache[maven_key]

                    release_time = await self._fetch_jar_release_time(maven_key)
                    sha1 = await self._fetch_jar_sha1(maven_key)

                    # Store in cache
                    self._maven_cache[maven_key] = (release_time, sha1)
                    return release_time, sha1
                return None, None

        metadata_list = await asyncio.gather(*[fetch_metadata(e) for e in loader_entries])
        logger.info(f"[Fabric] Finished metadata for {mc_version} (cache size: {len(self._maven_cache)})")
        release_times = [m[0] for m in metadata_list]
        sha1_hashes = [m[1] for m in metadata_list]

        result = FabricMetaVersionFile.from_fabric_loaders(
            mc_version=mc_version,
            loader_entries=loader_entries,
            release_times=release_times,
            sha1_hashes=sha1_hashes,
            installer_version=installer_version,
            uid=self.platform_uid
        )

        if result:
            logger.debug(f"[Fabric] Built meta for {mc_version} — {len(loader_entries)} loaders")

        return result

    async def _fetch_installer_version(self) -> Optional[str]:
        raw = await self.get_json(f"{URL}/installer")
        if not raw:
            return None

        installers = [FabricInstallerVersion(**v) for v in raw]

        for installer in installers:
            if installer.stable:
                return installer.version

        return installers[0].version if installers else None

    async def _fetch_jar_release_time(self, maven_key: str) -> Optional[str]:
        try:
            parts = maven_key.split(":")
            if len(parts) != 3:
                return None

            group_id, artifact_id, version = parts
            group_path = group_id.replace(".", "/")
            jar_url = f"{MAVEN_URL}/{group_path}/{artifact_id}/{version}/{artifact_id}-{version}.jar"

            session = await self._get_session()
            async with session.head(jar_url) as resp:
                if resp.status == 200:
                    last_modified = resp.headers.get("Last-Modified")
                    if last_modified:
                        dt = datetime.strptime(last_modified, "%a, %d %b %Y %H:%M:%S %Z")
                        return dt.isoformat()
        except Exception as e:
            logger.debug(f"[Fabric] Failed to get release time for {maven_key}: {e}")

        return None

    async def _fetch_jar_sha1(self, maven_key: str) -> Optional[str]:
        try:
            parts = maven_key.split(":")
            if len(parts) != 3:
                return None

            group_id, artifact_id, version = parts
            group_path = group_id.replace(".", "/")
            sha1_url = f"{MAVEN_URL}/{group_path}/{artifact_id}/{version}/{artifact_id}-{version}.jar.sha1"

            session = await self._get_session()
            async with session.get(sha1_url) as resp:
                if resp.status == 200:
                    sha1_hash = await resp.text()
                    return sha1_hash.strip()
        except Exception as e:
            logger.debug(f"[Fabric] Failed to get SHA1 for {maven_key}: {e}")

        return None