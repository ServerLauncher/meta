import logging
import asyncio
from typing import Optional

from meta.run.base_fetcher import BaseFetcher
from meta.models.paper_model import (
    PaperProjectResponse,
    PaperBuildsResponse,
    PaperMetaVersionFile,
    PaperMetaVersionEntry,
    PaperMetaVersion
)

URL = "https://api.papermc.io/v2/projects/paper"

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

class PaperFetcher(BaseFetcher):
    platform_id = "paper"
    platform_name = "Paper"
    platform_uid = "io.papermc.paper"

    async def fetch(self) -> Optional[tuple[PaperMetaVersion, dict[str, PaperMetaVersionFile]]]:
        logger.info("[Paper] Fetching project info...")
        
        raw_project = await self.get_json(URL)
        if not raw_project:
            logger.error("[Paper] Failed to fetch project info")
            return None

        project = PaperProjectResponse(**raw_project)
        mc_versions = list(reversed(project.versions))
        logger.info(f"[Paper] Loaded {len(mc_versions)} MC versions")

        semaphore = asyncio.Semaphore(10)

        async def fetch_one(mc_version: str):
            async with semaphore:
                logger.debug(f"[Paper] Fetching builds for {mc_version}")
                return await self._fetch_builds(mc_version)
        
        tasks = await asyncio.gather(*[fetch_one(v) for v in mc_versions])

        version_files: dict[str, PaperMetaVersionFile] = {}
        version_entries: list[PaperMetaVersionEntry] = []
        recommended: list[str] = []

        for mc_version, version_file in zip(mc_versions, tasks):
            if not version_file:
                logger.debug(f"[Paper] Skipping {mc_version} (no builds)")
                continue

            latest_build = version_file.builds[0].build if version_file.builds else ""

            version_files[mc_version] = version_file

            version_entries.append(PaperMetaVersionEntry(
                    mcVersion=mc_version,
                    latestBuild=latest_build,
                    sha256="",
                    url=f"{self.platform_uid}/{mc_version}.json"
                )
            )
            if not recommended:
                recommended.append(mc_version)

        logger.info(f"[Paper] Processed {len(version_entries)} MC versions")

        package = PaperMetaVersion(
            uid=self.platform_id,
            name=self.platform_name,
            recommended=recommended,
            versions=version_entries
        )

        return package, version_files

    async def _fetch_builds(self, mc_version: str) -> Optional[PaperMetaVersionFile]:
        raw = await self.get_json(f"{URL}/versions/{mc_version}/builds")
        if not raw:
            logger.error(f"[Paper] Failed to fetch builds for {mc_version}")
            return None
        
        response = PaperBuildsResponse(**raw)

        if not response.builds:
            logger.debug(f"[Paper] No builds for {mc_version}")
            return None
        
        result = PaperMetaVersionFile.from_paper_builds(
            mc_version=mc_version,
            builds=response.builds,
            uid=self.platform_uid            
        )
        
        if result:
            logger.debug(f"[Paper] Built meta for {mc_version} — {len(response.builds)} builds")

        return result