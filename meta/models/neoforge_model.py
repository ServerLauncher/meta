from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional
from pydantic_xml import BaseXmlModel, element

from . import MetaDownload, MetaBuild, MetaVersionEntry, MetaPackage, MetaVersionFile

MAVEN_BASE = "https://maven.neoforged.net/releases/net/neoforged/neoforge"

class MavenVersions(BaseXmlModel, tag="versions"):
    versions: list[str] = element(tag="version", default=[])

class MavenVersioning(BaseXmlModel, tag="versioning"):
    latest: Optional[str] = element(default=None)
    release: Optional[str] = element(default=None)
    versions: MavenVersions = MavenVersions()

    def all_versions(self) -> list[str]:
        return self.versions.versions  

class MavenMetadata(BaseXmlModel, tag="metadata"):
    groupId: str = element()
    artifactId: str = element()
    versioning: MavenVersioning

    def all_versions(self) -> list[str]:
        return self.versioning.all_versions()

    def latest_version(self) -> Optional[str]:
        return self.versioning.release or self.versioning.latest

def _infer_type(mc_version: str):
    lower = mc_version.lower()
    if any(tag in lower for tag in ("beta", "rc", "alpha")):
        return "snapshot"
    return "stable"

def _mc_version_from_neoforge(version: str) -> str:
    clean = version.split('+')[0].split('-')[0]
    parts = clean.split('.')

    try:
        major = int(parts[0])
    except ValueError:
        return version

    if major == 0:
        return parts[1] if len(parts) >= 2 else version

    if major >= 26:
        return f"{parts[0]}.{parts[1]}"
    else:
        if len(parts) >= 2:
            minor = int(parts[1])
            return f"1.{parts[0]}.{parts[1]}" if minor != 0 else f"1.{parts[0]}"
        return f"1.{parts[0]}"

class NeoForgeRawBuild(BaseModel):
    version: str
    sha1: str = ""
    release_time: Optional[str] = None

    @property
    def installer_name(self) -> str:
        return f"neoforge-{self.version}-installer.jar"

    @property
    def installer_url(self) -> str:
        return f"{MAVEN_BASE}/{self.version}/{self.installer_name}"

    @property
    def sha1_url(self) -> str:
        return f"{self.installer_url}.sha1"

    @property
    def mc_version(self) -> str:
        return _mc_version_from_neoforge(self.version)

    @property
    def type(self) -> str:
        return _infer_type(self.version)

    @property
    def recommended(self) -> bool:
        return self.type == "stable"

    @classmethod
    def create(cls, version: str, sha1: str, release_time: Optional[datetime] = None) -> "NeoForgeRawBuild":
        return cls(
            version=version,
            sha1=sha1,
            release_time=release_time.isoformat() if release_time else None,
        )


class NeoForgeMetaBuild(MetaBuild):
    @classmethod
    def from_raw(cls, raw: NeoForgeRawBuild) -> "NeoForgeMetaBuild":
        return cls(
            build=raw.version,
            type=raw.type,
            releaseTime=raw.release_time if raw.release_time else None,
            recommended=raw.recommended,
            download=MetaDownload(
                name=raw.installer_name,
                url=raw.installer_url,
                sha1=raw.sha1,
            )
        )
class NeoForgeMetaVersionFile(MetaVersionFile):
    builds: list[NeoForgeMetaBuild]

    @classmethod
    def from_raw(cls, raw: NeoForgeRawBuild, uid: str) -> "NeoForgeMetaVersionFile":
        return cls(
            uid=uid,
            mcVersion=raw.mc_version,
            builds=[NeoForgeMetaBuild.from_raw(raw)],
        )

class NeoForgeMetaVersionEntry(MetaVersionEntry):
    type: str = "stable"

class NeoForgeMetaVersion(MetaPackage):
    versions: list[NeoForgeMetaVersionEntry]