from pydantic import BaseModel, Field
from typing import Optional

from . import MetaDownload, MetaBuild, MetaVersionEntry, MetaPackage, MetaVersionFile

class PaperApplicationDownload(BaseModel):
    name: str
    sha256: str

class PaperBuildDownloads(BaseModel):
    application: Optional[PaperApplicationDownload] = None

class PapeeChanges(BaseModel):
    commit: str
    summary: str
    message: str

class PaperBuild(BaseModel):
    build: int
    time: str
    channel: str
    promoted: bool
    changes: list[PapeeChanges] = []
    downloads: PaperBuildDownloads

    @property
    def application(self) -> Optional[PaperApplicationDownload]:
        return self.downloads.application
    
    @property
    def is_stable(self) -> bool:
        return self.channel == "STABLE" or self.promoted
    
class PaperBuildsResponse(BaseModel):
    version: str
    builds:  list[PaperBuild]

    model_config = {"extra": "ignore"}

class PaperProjectResponse(BaseModel):
    versions: list[str]

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
                url=f"https://api.papermc.io/v2/projects/paper/versions/{mc_version}/builds/{build.build}/downloads/{build.application.name}",
                sha256=build.application.sha256
            )
        )
class PaperMetaVersionFile(MetaVersionFile):
    builds: list[PaperMetaBuild]

    @classmethod
    def from_paper_builds(cls, mc_version: str, builds: list[PaperBuild], uid: str) -> "PaperMetaVersionFile":
        meta_builds = []
        
        for b in reversed(builds):
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