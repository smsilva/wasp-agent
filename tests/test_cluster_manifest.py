def test_manifest_build_defaults():
    from wasp.resources.cluster import ClusterManifest

    manifest = ClusterManifest.build(name="edge")

    assert manifest.metadata.name == "edge"
    assert manifest.kind == "Cluster"
    assert manifest.apiVersion == "wasp.silvios.me/v1alpha1"
    assert manifest.spec.kubernetesVersion == "1.34"


def test_manifest_build_explicit_version():
    from wasp.resources.cluster import ClusterManifest

    manifest = ClusterManifest.build(name="edge", kubernetes_version="1.33")

    assert manifest.spec.kubernetesVersion == "1.33"


def test_manifest_yaml_output():
    import yaml
    from wasp.resources.cluster import ClusterManifest

    manifest = ClusterManifest.build("edge")
    yaml_str = yaml.dump(
        manifest.model_dump(), default_flow_style=False, sort_keys=False
    )
    data = yaml.safe_load(yaml_str)

    assert data["apiVersion"] == "wasp.silvios.me/v1alpha1"
    assert data["kind"] == "Cluster"
    assert data["metadata"]["name"] == "edge"
    assert data["spec"]["kubernetesVersion"] == "1.34"
