from pydantic import BaseModel, Field
from typing import Optional

from . import MetaDownload, MetaBuild, MetaVersionEntry, MetaPackage, MetaVersionFile

class PaperChecksum(BaseModel):
    sha256: str


class PaperApplicationDownload(BaseModel):
    name: str
    checksums: PaperChecksum
    size: int
    url: str


class PaperBuildDownloads(BaseModel):
    application: Optional[PaperApplicationDownload] = Field(
        alias="server:default",
        default=None
    )

    model_config = {
        "populate_by_name": True
    }


class PaperCommit(BaseModel):
    sha: str
    time: str
    message: str


class PaperBuild(BaseModel):
    id: int
    time: str
    channel: str

    commits: list[PaperCommit] = []

    downloads: PaperBuildDownloads

    @property
    def build(self) -> int:
        return self.id

    @property
    def application(self) -> Optional[PaperApplicationDownload]:
        return self.downloads.application
    
class PaperBuildsResponse(BaseModel):
    builds:  list[PaperBuild]

    model_config = {"extra": "ignore"}

class PaperProjectResponse(BaseModel):
    versions: dict[str, list[str]]

    model_config = {"extra": "ignore"}

class PaperMetaBuild(MetaBuild):
    @classmethod
    def from_paper(cls, mc_version: str, build: PaperBuild, recommended: bool) -> Optional["PaperMetaBuild"]:
        if not build.application:
            return None
        
        return cls(
            build=str(build.build),
            type=build.channel.lower(),
            releaseTime=build.time,
            recommended=recommended,
            download=MetaDownload(
                name=build.application.name,
                url=build.application.url,
                sha256=build.application.checksums.sha256
            )
        )
class PaperMetaVersionFile(MetaVersionFile):
    builds: list[PaperMetaBuild]

    @classmethod
    def from_paper_builds(cls, mc_version: str, builds: list[PaperBuild], uid: str) -> "PaperMetaVersionFile":
        meta_builds = []
        
        for b in builds:
            if not b.application:
                continue

            meta_build = PaperMetaBuild.from_paper(
                mc_version=mc_version, 
                build=b, 
                recommended=False
            )
            if meta_build:
                meta_builds.append(meta_build)
        
        if meta_builds:
            meta_builds[0].recommended = True 
        
        return cls(
            uid=uid,
            mcVersion=mc_version,
            builds=meta_builds
        )

class PaperMetaVersionEntry(MetaVersionEntry):
    latest_build: str = Field(alias="latestBuild")

    model_config = {"populate_by_name": True}

class PaperMetaVersion(MetaPackage):
    versions: list[PaperMetaVersionEntry]