from pydantic import BaseModel, Field

from wasp.resources.base import MetadataSpec, ResourceManifest

PLATFORM_GROUP = "wasp.silvios.me"
PLATFORM_VERSION = "v1alpha1"
PLATFORM_PLURAL = "platforms"


class ServiceSpec(BaseModel):
    name: str


class RegionSpec(BaseModel):
    name: str
    endpoint: str


class PlatformSpec(BaseModel):
    domain: str
    regions: list[RegionSpec]
    services: list[ServiceSpec] = Field(
        default_factory=lambda: [
            ServiceSpec(name=s) for s in ["auth", "discovery", "callback", "portal"]
        ]
    )


class PlatformManifest(ResourceManifest):
    kind: str = "Platform"
    spec: PlatformSpec

    @classmethod
    def build(cls, name: str, domain: str, regions: list[str]) -> "PlatformManifest":
        return cls(
            metadata=MetadataSpec(name=name),
            spec=PlatformSpec(
                domain=domain,
                regions=[
                    RegionSpec(name=r, endpoint=f"gateway.{r}.{name}.{domain}")
                    for r in regions
                ],
            ),
        )
