from pydantic import BaseModel, Field
from typing import Optional

from . import MetaDownload, MetaBuild, MetaVersionEntry, MetaPackage, MetaVersionFile

MAVEN_BASE = "https://maven.minecraftforge.net/net/minecraftforge/forge"

class ForgePromos(BaseModel):
    homepage: str
    promos: dict[str, str]

    def get_recommended(self, mc_version: str) -> Optional[str]:
        return self.promos.get(f"{mc_version}-recommended")

    def get_latest(self, mc_version: str) -> Optional[str]:
        return self.promos.get(f"{mc_version}-latest")

    def all_mc_versions(self) -> list[str]:
        versions = set()
        for key in self.promos:
            mc = key.rsplit("-", 1)[0]
            versions.add(mc)
        return list(versions)


ForgeVersionIndex = dict[str, list[str]]

class ForgeRawBuild(BaseModel):
    long_version: str
    mc_version: str
    forge_version: str
    sha1: str = ""
    recommended: bool = False
    release_time: Optional[str] = None

    @property
    def installer_name(self) -> str:
        return f"forge-{self.long_version}-installer.jar"

    @property
    def installer_url(self) -> str:
        return f"{MAVEN_BASE}/{self.long_version}/{self.installer_name}"

    @property
    def sha1_url(self) -> str:
        return f"{self.installer_url}.sha1"

    @property
    def type(self) -> str:
        return "stable" if self.recommended else "snapshot"

    @classmethod
    def from_long_version(cls, long_version: str, recommended: bool = False) -> "ForgeRawBuild":
        mc_version, forge_version = long_version.split("-", 1)
        return cls(
            long_version=long_version,
            mc_version=mc_version,
            forge_version=forge_version,
            recommended=recommended,
        )

class ForgeMetaBuild(MetaBuild):
    @classmethod
    def from_raw(cls, raw: ForgeRawBuild) -> "ForgeMetaBuild":
        return cls(
            build=raw.long_version,
            type=raw.type,
            releaseTime=raw.release_time,
            recommended=raw.recommended,
            download=MetaDownload(
                name=raw.installer_name,
                url=raw.installer_url,
                sha1=raw.sha1,
            )
        )

class ForgeMetaVersionFile(MetaVersionFile):
    builds: list[ForgeMetaBuild]

    @classmethod
    def from_raw(cls, raw: ForgeRawBuild, uid: str) -> "ForgeMetaVersionFile":
        return cls(
            uid=uid,
            mcVersion=raw.mc_version,
            builds=[ForgeMetaBuild.from_raw(raw)],
        )

class ForgeMetaVersionEntry(MetaVersionEntry):
    type: str = "stable"

class ForgeMetaVersion(MetaPackage):
    versions: list[ForgeMetaVersionEntry]