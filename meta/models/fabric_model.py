from pydantic import BaseModel, Field
from typing import Optional

from . import MetaDownload, MetaBuild, MetaVersionEntry, MetaPackage, MetaVersionFile

class FabricLoader(BaseModel):
    separator: Optional[str] = None
    build: Optional[int] = None
    maven: Optional[str] = None
    version: str
    stable: bool

    model_config = {"extra": "ignore"}

class FabricLoaderEntry(BaseModel):
    loader: FabricLoader
    intermediary: Optional[dict] = None
    launcherMeta: Optional[dict] = None

    model_config = {"extra": "ignore"}

class FabricGameVersion(BaseModel):
    version: str
    stable: bool

    model_config = {"extra": "ignore"}

class FabricInstallerVersion(BaseModel):
    url: Optional[str] = None
    maven: Optional[str] = None
    version: str
    stable: bool

    model_config = {"extra": "ignore"}

class FabricMetaBuild(MetaBuild):
    @classmethod
    def from_fabric(cls, mc_version: str, loader_entry: FabricLoaderEntry, installer_version: str, recommended: bool, release_time: Optional[str] = None, sha1: Optional[str] = None) -> "FabricMetaBuild":
        loader = loader_entry.loader
        loader_version = loader.version

        return cls(
            build=loader_version,
            type="stable" if loader.stable else "snapshot",
            releaseTime=release_time,
            recommended=recommended,
            download=MetaDownload(
                name=f"fabric-server-{mc_version}-{loader_version}.jar",
                url=f"https://meta.fabricmc.net/v2/versions/loader/{mc_version}/{loader_version}/{installer_version}/server/jar",
                sha1=sha1
            )
        )

class FabricMetaVersionFile(MetaVersionFile):
    builds: list[FabricMetaBuild]

    @classmethod
    def from_fabric_loaders(cls, mc_version: str, loader_entries: list[FabricLoaderEntry], release_times: list[Optional[str]], sha1_hashes: list[Optional[str]], installer_version: str, uid: str) -> "FabricMetaVersionFile":
        meta_builds = []
        marked_recommended = False

        for entry, release_time, sha1 in zip(loader_entries, release_times, sha1_hashes):
            is_recommended = False
            if not marked_recommended and entry.loader.stable:
                is_recommended = True
                marked_recommended = True

            meta_build = FabricMetaBuild.from_fabric(
                mc_version=mc_version,
                loader_entry=entry,
                installer_version=installer_version,
                recommended=is_recommended,
                release_time=release_time,
                sha1=sha1
            )
            meta_builds.append(meta_build)

        if meta_builds and not any(b.recommended for b in meta_builds):
            meta_builds[0].recommended = True

        return cls(
            uid=uid,
            mcVersion=mc_version,
            builds=meta_builds
        )

class FabricMetaVersionEntry(MetaVersionEntry):
    pass

class FabricMetaVersion(MetaPackage):
    versions: list[FabricMetaVersionEntry]
