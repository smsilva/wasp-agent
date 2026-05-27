from pydantic import BaseModel

WASP_API_VERSION = "wasp.silvios.me/v1alpha1"


class MetadataSpec(BaseModel):
    name: str


class ResourceManifest(BaseModel):
    apiVersion: str = WASP_API_VERSION
    metadata: MetadataSpec
