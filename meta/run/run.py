import asyncio
import json
import logging
from datetime import datetime, timezone
import os
from pathlib import Path

from meta.run.mojang_fetcher import MojangFetcher
from meta.run.paper_fetcher import PaperFetcher
from meta.run.purpur_fetcher import PurpurFetcher
from meta.run.fabric_fetcher import FabricFetcher
from meta.run.neoforge_fetcher import NeoForgeFetcher
from meta.run.forge_fetcher import ForgeFetcher
from meta.run.java_fetcher import MojangJavaFetcher, AdoptiumJavaFetcher
from meta.models import MetaIndex, MetaIndexEntry
from meta.common import sha256, write_json

logging.basicConfig(level=logging.INFO)

async def main():
    logging.info("Starting meta build process")

    fetchers = [MojangFetcher(), PaperFetcher(), PurpurFetcher(), NeoForgeFetcher(),
                FabricFetcher(), MojangJavaFetcher(), AdoptiumJavaFetcher(), ForgeFetcher()]
    os.makedirs("dist", exist_ok=True)
    output = Path("dist")

    try:
        logging.info(f"Running {len(fetchers)} fetcher(s)...")

        results = await asyncio.gather(*[f.fetch() for f in fetchers])

        platform_entries = []

        for fetcher, result in zip(fetchers, results):
            logging.info(f"Processing platform: {fetcher.platform_name}")

            if not result:
                logging.error(f"Fetcher failed: {fetcher.platform_name}")
                continue

            package, versions_files = result
            uid = fetcher.platform_uid
            platform_dir = output / uid
            platform_dir.mkdir(parents=True, exist_ok=True)

            logging.info(f"Writing versions for {uid} ({len(versions_files)} items)")

            for mc_version, version_file in versions_files.items():
                try:
                    version_json = version_file.model_dump(by_alias=True)
                    version_str = json.dumps(version_json)

                    for entry in package.versions:
                        if getattr(entry, "mc_version", None) == mc_version or getattr(entry, "java_version", None) == mc_version:
                            entry.sha256 = sha256(version_str)
                            break

                    write_json(platform_dir / f"{mc_version}.json", version_json)
                    logging.debug(f"Saved version {mc_version}")

                except Exception as e:
                    logging.exception(f"Failed processing version {mc_version}: {e}")

            logging.info(f"Writing package.json for {uid}")

            package_json = package.model_dump(by_alias=True)
            package_str = json.dumps(package_json)

            write_json(platform_dir / "package.json", package_json)

            platform_entries.append(
                MetaIndexEntry(
                    uid=uid,
                    name=fetcher.platform_name,
                    sha256=sha256(package_str),
                    url=f"{uid}/package.json",
                )
            )

        logging.info("Building index.json")

        index = MetaIndex(
            generatedAt=datetime.now(timezone.utc).isoformat(),
            platforms=platform_entries,
        )

        write_json(output / "index.json", index.model_dump(by_alias=True))

        logging.info("Meta build completed successfully")

    except Exception as e:
        logging.exception(f"Fatal error during build: {e}")

    finally:
        logging.info("Closing fetchers...")
        await asyncio.gather(*[f.close() for f in fetchers])
        logging.info("Shutdown complete")

if __name__ == "__main__":
    asyncio.run(main())