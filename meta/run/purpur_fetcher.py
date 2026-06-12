import logging
import asyncio
from typing import Optional

from meta.run.base_fetcher import BaseFetcher
from meta.models.purpur_model import (
    PurpurProjectResponse,
    PurpurBuildsResponse,
    PurpurBuildInfo,
    PurpurMetaVersionFile,
    PurpurMetaVersionEntry,
    PurpurMetaVersion
)

URL = "https://api.purpurmc.org/v2/purpur"

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

class PurpurFetcher(BaseFetcher):
    platform_id = "purpur"
    platform_name = "Purpur"
    platform_uid = "build.purpurmc.purpur"

    async def fetch(self) -> Optional[tuple[PurpurMetaVersion, dict[str, PurpurMetaVersionFile]]]:
        logger.info("[Purpur] Fetching project info...")

        raw_project = await self.get_json(URL)
        if not raw_project:
            logger.error("[Purpur] Failed to fetch project info")
            return None

        project = PurpurProjectResponse(**raw_project)
        mc_versions = list(reversed(project.versions))
        logger.info(f"[Purpur] Loaded {len(mc_versions)} MC versions")

        semaphore = asyncio.Semaphore(10)

        async def fetch_one(mc_version: str):
            async with semaphore:
                logger.debug(f"[Purpur] Fetching builds for {mc_version}")
                return await self._fetch_builds(mc_version)

        tasks = await asyncio.gather(*[fetch_one(v) for v in mc_versions])

        version_files: dict[str, PurpurMetaVersionFile] = {}
        version_entries: list[PurpurMetaVersionEntry] = []
        recommended: list[str] = []

        for mc_version, version_file in zip(mc_versions, tasks):
            if not version_file:
                logger.debug(f"[Purpur] Skipping {mc_version} (no builds)")
                continue

            latest_build = version_file.builds[0].build if version_file.builds else ""

            version_files[mc_version] = version_file

            version_entries.append(PurpurMetaVersionEntry(
                    mcVersion=mc_version,
                    latestBuild=latest_build,
                    sha256="",
                    url=f"{self.platform_uid}/{mc_version}.json"
                )
            )
            if not recommended:
                recommended.append(mc_version)

        logger.info(f"[Purpur] Processed {len(version_entries)} MC versions")

        package = PurpurMetaVersion(
            uid=self.platform_id,
            name=self.platform_name,
            recommended=recommended,
            versions=version_entries
        )

        return package, version_files

    async def _fetch_builds(self, mc_version: str) -> Optional[PurpurMetaVersionFile]:
        raw = await self.get_json(f"{URL}/{mc_version}")
        if not raw:
            logger.error(f"[Purpur] Failed to fetch builds for {mc_version}")
            return None

        response = PurpurBuildsResponse(**raw)

        if not response.all_builds:
            logger.debug(f"[Purpur] No builds for {mc_version}")
            return None

        semaphore = asyncio.Semaphore(10)

        async def fetch_build_info(build_num: int):
            async with semaphore:
                raw_info = await self.get_json(f"{URL}/{mc_version}/{build_num}")
                if not raw_info:
                    return None
                return build_num, PurpurBuildInfo(**raw_info)

        build_tasks = await asyncio.gather(*[fetch_build_info(b) for b in response.all_builds])
        builds_with_info = [item for item in build_tasks if item is not None]

        builds_with_info.sort(key=lambda x: x[0], reverse=True)

        if not builds_with_info:
            logger.debug(f"[Purpur] No valid builds for {mc_version}")
            return None

        result = PurpurMetaVersionFile.from_purpur_builds(
            mc_version=mc_version,
            builds=builds_with_info,
            uid=self.platform_uid
        )

        if result:
            logger.debug(f"[Purpur] Built meta for {mc_version} — {len(builds_with_info)} builds")

        return result