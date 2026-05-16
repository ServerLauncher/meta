import logging
import asyncio
from typing import Optional

from meta.run.base_fetcher import BaseFetcher
from meta.models.java_model import (
    AdoptiumEntry,
    MojangJavaRuntime,
    JavaBuild,
    JavaVersionFile,
    JavaVersionEntry,
    JavaMetaPackage
)

ADOPTIUM_API = "https://api.adoptium.net/v3/assets/feature_releases/{major}/ga?image_type=jre"
MOJANG_JAVA_URL = ("https://piston-meta.mojang.com/v1/products/java-runtime/2ec0cc96c44e5a76b9c8b7c39df7210883d12871/all.json")

JAVA_MAJORS = [8, 11, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26]

MOJANG_COMPONENTS = {
    "jre-legacy": 8,
    "java-runtime-alpha": 16,
    "java-runtime-beta": 17,
    "java-runtime-gamma": 17,
    "java-runtime-gamma-snapshot": 17,
    "java-runtime-delta": 21,
    "java-runtime-epsilon": 25
}
MOJANG_OS_MAP = {
    "linux": "linux-x64",
    "linux-i386": "linux-x86",
    "mac-os": "mac-x64",
    "mac-os-arm64": "mac-aarch64",
    "windows-x64": "windows-x64",
    "windows-x86": "windows-x86",
    "windows-arm64": "windows-arm64",
}

ADOPTIUM_PLATFORM_MAP = {
    ("linux", "x64"): "linux-x64",
    ("linux", "aarch64"): "linux-aarch64",
    ("linux", "x86"): "linux-x86",
    ("alpine-linux", "x64"): "linux-alpine-x64",
    ("windows", "x64"): "windows-x64",
    ("windows", "x86"): "windows-x86",
    ("windows", "aarch64"): "windows-arm64",
    ("mac", "x64"): "mac-x64",
    ("mac", "aarch64"): "mac-aarch64",
}

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

class MojangJavaFetcher(BaseFetcher):
    platform_id = "java"
    platform_name = "Java Runtimes"
    platform_uid = "net.minecraft.java"

    async def fetch(self) -> Optional[tuple[JavaMetaPackage, dict[str, JavaVersionFile]]]:
        logger.info("[MojangJava] Fetching Java index...")

        raw = await self.get_json(MOJANG_JAVA_URL)
        if not raw:
            return None
        
        builds_by_major: dict[int, dict[str, list[JavaBuild]]] = {}
        for mojang_os, our_platform in MOJANG_OS_MAP.items():
            os_component = raw.get(mojang_os, {})

            for component, major in MOJANG_COMPONENTS.items():
                runtime_list = os_component.get(component, [])
                if not runtime_list:
                    continue
                
                runtime = MojangJavaRuntime(**runtime_list[0])

                java_build = JavaBuild.from_mojang(runtime, recommended=False, component=component, major=major)

                if major not in builds_by_major:
                    builds_by_major[major] = {}

                if our_platform not in builds_by_major[major]:
                    builds_by_major[major][our_platform] = []

                builds_by_major[major][our_platform].append(java_build)
            
            for _, platform_builds in builds_by_major.items():
                for _, builds in platform_builds.items():
                    builds[0].recommended = True
            
            version_files: dict[str, JavaVersionFile] = {}
            version_entries: list[JavaVersionEntry] = []

            for major, platforms in sorted(builds_by_major.items()):
                key = f"java{major}"

                version_file = JavaVersionFile(
                    uid=key,
                    major=major,
                    platforms=platforms
                )

                version_files[key] = version_file

                version_entries.append(JavaVersionEntry(
                    java_version=key,
                    sha256="",
                    url=f"{self.platform_uid}/{key}.json",
                    major=major
                ))

                total_builds = sum(len(b) for b in platforms.values())
                logger.info(f"[MojangJava] Java {major} — {len(platforms)} platforms, {total_builds} builds")

        meta_package = JavaMetaPackage(
            uid=self.platform_uid,
            name=self.platform_name,
            recommended=[],
            versions=version_entries
        )

        logger.info(f"[MojangJava] Done — {len(version_files)} Java versions")
        return meta_package, version_files

class AdoptiumJavaFetcher(BaseFetcher):
    platform_id   = "java"
    platform_name = "Java Runtimes"
    platform_uid  = "net.adoptium.java"

    async def fetch(self) -> Optional[tuple[JavaMetaPackage, dict[str, JavaVersionFile]]]:
        logger.info("[Adoptium] Fetching Java runtimes...")

        semaphore = asyncio.Semaphore(5)

        async def fetch_one(major: int):
            async with semaphore:
                return await self._fetch_major(major=major)

        results = await asyncio.gather(*[fetch_one(m) for m in JAVA_MAJORS])

        version_files:   dict[str, JavaVersionFile] = {}
        version_entries: list[JavaVersionEntry]     = []

        for major, result in zip(JAVA_MAJORS, results):
            if not result:
                continue

            key = f"java{major}"
            version_files[key] = result

            version_entries.append(JavaVersionEntry(
                javaVersion=key,
                major=major,
                sha256="",
                url=f"{self.platform_uid}/{key}.json"
            ))

        package = JavaMetaPackage(
            uid=self.platform_uid,
            name=self.platform_name,
            recommended=[],
            versions=version_entries
        )

        logger.info(f"[Adoptium] Done — {len(version_files)} Java versions")
        return package, version_files

    async def _fetch_major(self, major: int) -> Optional[JavaVersionFile]:
        url = ADOPTIUM_API.format(major=major)

        raw = await self.get_json(url)
        if not raw:
            logger.warning(f"[Adoptium] Failed to fetch Java {major}")
            return None

        entries = [AdoptiumEntry(**e) for e in raw]

        platforms: dict[str, list[JavaBuild]] = {}

        all_builds: list[tuple[AdoptiumEntry, any]] = []

        for entry in entries:
            for binary in entry.binaries:
                if binary.image_type != "jre":
                    continue

                all_builds.append((entry, binary))

        if not all_builds:
            logger.warning(f"[Adoptium] No JRE entries for Java {major}")
            return None

        latest_build = max(all_builds, key=lambda x: (
            x[0].version_data.major, 
            x[0].version_data.minor, 
            x[0].version_data.security, 
            x[0].version_data.build or 0))[0].release_name

        for entry, binary in all_builds:
            key = (binary.os, binary.architecture)

            platform_name = ADOPTIUM_PLATFORM_MAP.get(key)
            if not platform_name:
                logger.debug(f"[Adoptium] Unknown platform {key}, skipping")
                continue

            if platform_name not in platforms:
                platforms[platform_name] = []

            recommended = entry.release_name == latest_build

            build = JavaBuild.from_adoptium(
                entry=entry,
                binary=binary,
                recommended=recommended
            )

            platforms[platform_name].append(build)

        for builds in platforms.values():
            builds.sort(
                key=lambda b: (
                    b.version_info.major,
                    b.version_info.minor,
                    b.version_info.security,
                    b.version_info.build
                ),
                reverse=True
            )

        total = sum(len(b) for b in platforms.values())
        logger.info(f"[Adoptium] Java {major} — {len(platforms)} platforms, {total} builds")

        return JavaVersionFile(
            uid=f"java{major}",
            major=major,
            platforms=platforms
        )