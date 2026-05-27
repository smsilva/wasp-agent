def test_resource_manifest_default_api_version():
    from wasp.resources.base import MetadataSpec, ResourceManifest

    class FakeSpec(ResourceManifest):
        kind: str = "Fake"
        spec: dict = {}

    m = FakeSpec(metadata=MetadataSpec(name="x"))
    assert m.apiVersion == "wasp.silvios.me/v1alpha1"
    assert m.metadata.name == "x"
    assert m.kind == "Fake"


def test_resource_manifest_exposes_constant():
    from wasp.resources.base import WASP_API_VERSION

    assert WASP_API_VERSION == "wasp.silvios.me/v1alpha1"


def test_resources_package_reexports():
    from wasp.resources import MetadataSpec, ResourceManifest

    assert ResourceManifest.__name__ == "ResourceManifest"
    assert MetadataSpec.__name__ == "MetadataSpec"
