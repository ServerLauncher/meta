from pydantic import BaseModel, Field
from typing import Optional

from . import MetaDownload, MetaBuild, MetaVersionEntry, MetaPackage, MetaVersionFile

class PurpurApplicationDownload(BaseModel):
    name: str
    md5: str

class PurpurBuildDownloads(BaseModel):
    application: Optional[PurpurApplicationDownload] = None

class PurpurBuild(BaseModel):
    build: int
    timestamp: int
    md5: str

    @property
    def application(self) -> Optional[PurpurApplicationDownload]:
        return PurpurApplicationDownload(
            name=f"purpur-{self.build}.jar",
            md5=self.md5
        )

class PurpurBuildsResponse(BaseModel):
    project: str
    version: str
    builds: dict

    model_config = {"extra": "ignore"}

    @property
    def all_builds(self) -> list[int]:
        return self.builds.get("all", [])

class PurpurProjectResponse(BaseModel):
    project: str
    versions: list[str]

    model_config = {"extra": "ignore"}

class PurpurBuildInfo(BaseModel):
    build: int
    timestamp: int
    md5: Optional[str] = None

    model_config = {"extra": "ignore"}

class PurpurMetaBuild(MetaBuild):
    @classmethod
    def from_purpur(cls, mc_version: str, build_num: int, build_info: PurpurBuildInfo, recommended: bool) -> "PurpurMetaBuild":
        from datetime import datetime, timezone

        release_time = ""
        if build_info.timestamp:
            release_time = datetime.fromtimestamp(build_info.timestamp / 1000, timezone.utc).isoformat()

        return cls(
            build=str(build_num),
            type="default",
            releaseTime=release_time,
            recommended=recommended,
            download=MetaDownload(
                name=f"purpur-{mc_version}-{build_num}.jar",
                url=f"https://api.purpurmc.org/v2/purpur/{mc_version}/{build_num}/download",
                md5=build_info.md5
            )
        )

class PurpurMetaVersionFile(MetaVersionFile):
    builds: list[PurpurMetaBuild]

    @classmethod
    def from_purpur_builds(cls, mc_version: str, builds: list[tuple[int, PurpurBuildInfo]], uid: str) -> "PurpurMetaVersionFile":
        meta_builds = []

        for idx, (build_num, build_info) in enumerate(builds):
            is_recommended = (idx == 0)

            meta_build = PurpurMetaBuild.from_purpur(
                mc_version=mc_version,
                build_num=build_num,
                build_info=build_info,
                recommended=is_recommended
            )
            meta_builds.append(meta_build)

        return cls(
            uid=uid,
            mcVersion=mc_version,
            builds=meta_builds
        )

class PurpurMetaVersionEntry(MetaVersionEntry):
    latest_build: str = Field(alias="latestBuild")

    model_config = {"populate_by_name": True}

class PurpurMetaVersion(MetaPackage):
    versions: list[PurpurMetaVersionEntry]
