from pydantic import BaseModel, Field
from typing import Optional

class MetaDownload(BaseModel):
    name: str
    url: str
    sha1: Optional[str] = None
    sha256: Optional[str] = None
    md5: Optional[str] = None

    model_config = {"populate_by_name": True}

class MetaBuild(BaseModel):
    build: Optional[str] = None
    type: str = "release"
    release_time: Optional[str] = Field(None, alias="releaseTime")
    recommended: bool = False
    download: MetaDownload

    model_config = {"populate_by_name": True}

class MetaVersionEntry(BaseModel):
    mc_version: str = Field(alias="mcVersion")
    sha256: str
    url: str

    model_config = {"populate_by_name": True}

class MetaPackage(BaseModel):
    format_version: int = Field(1, alias="formatVersion")
    uid: str
    name: str
    recommended: list[str] = []
    versions: list[MetaVersionEntry]

    model_config = {"populate_by_name": True}

class MetaVersionFile(BaseModel):
    format_version: int = Field(1, alias="formatVersion")
    uid: str
    mc_version: str = Field(alias="mcVersion")
    builds: list[MetaBuild]

    model_config = {"populate_by_name": True}

class MetaIndexEntry(BaseModel):
    uid: str
    name: str
    sha256: str
    url: str

class MetaIndex(BaseModel):
    format_version: int = Field(1, alias="formatVersion")
    generated_at: str = Field(alias="generatedAt")
    platforms: list[MetaIndexEntry]

    model_config = {"populate_by_name": True}