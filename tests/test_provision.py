import pytest


def test_manifest_build():
    from tools.provision import PlatformManifest

    manifest = PlatformManifest.build(
        name="wp2",
        domain="wasp.silvios.me",
        regions=["us-east-1", "sa-east-1"],
    )

    assert manifest.name == "wp2"
    assert manifest.spec.domain == "wasp.silvios.me"
    assert len(manifest.spec.regions) == 2
    r0 = manifest.spec.regions[0]
    assert r0.name == "us-east-1"
    assert r0.endpoint == "gateway.us-east-1.wp2.wasp.silvios.me"
    r1 = manifest.spec.regions[1]
    assert r1.endpoint == "gateway.sa-east-1.wp2.wasp.silvios.me"
    assert [s.name for s in manifest.spec.services] == [
        "auth", "discovery", "callback", "portal"
    ]


def test_manifest_yaml_output():
    import yaml
    from tools.provision import PlatformManifest

    manifest = PlatformManifest.build("wp2", "wasp.silvios.me", ["us-east-1"])
    yaml_str = yaml.dump(manifest.model_dump(), default_flow_style=False, sort_keys=False)
    data = yaml.safe_load(yaml_str)

    assert data["apiVersion"] == "wasp.silvios.me/v1alpha1"
    assert data["kind"] == "Platform"
    assert data["name"] == "wp2"
    assert data["spec"]["domain"] == "wasp.silvios.me"
    assert data["spec"]["regions"][0]["endpoint"] == "gateway.us-east-1.wp2.wasp.silvios.me"
    assert len(data["spec"]["services"]) == 4
    assert [s["name"] for s in data["spec"]["services"]] == [
        "auth", "discovery", "callback", "portal"
    ]


def test_provision_commits(monkeypatch):
    from unittest.mock import MagicMock
    from tools.provision import provision_platform_instance

    mock_github_cls = MagicMock()
    mock_repo = MagicMock()
    mock_commit = MagicMock()
    mock_commit.sha = "abc123def456"
    mock_github_cls.return_value.get_repo.return_value = mock_repo
    mock_repo.create_file.return_value = {"commit": mock_commit, "content": MagicMock()}

    monkeypatch.setenv("GH_PAT", "fake-pat")
    monkeypatch.setattr("tools.provision.Github", mock_github_cls)

    result = provision_platform_instance(
        name="wp2",
        domain="wasp.silvios.me",
        regions=["us-east-1"],
        requested_by="alice",
    )

    mock_github_cls.assert_called_once_with("fake-pat")
    mock_github_cls.return_value.get_repo.assert_called_once_with("smsilva/wasp-gitops")
    call_kwargs = mock_repo.create_file.call_args.kwargs
    assert call_kwargs["path"] == "infrastructure/tenants/wp2.yaml"
    assert call_kwargs["branch"] == "dev"
    assert "feat(tenants): provision wp2" in call_kwargs["message"]
    assert "Requested by: alice" in call_kwargs["message"]
    assert result["status"] == "provisioning"
    assert "wp2" in result["message"]


def test_provision_missing_pat(monkeypatch):
    from unittest.mock import MagicMock
    from tools.provision import provision_platform_instance

    monkeypatch.delenv("GH_PAT", raising=False)
    mock_github_cls = MagicMock()
    monkeypatch.setattr("tools.provision.Github", mock_github_cls)

    result = provision_platform_instance(name="wp2")

    assert result["status"] == "error"
    assert result["message"] == "Provisioning failed. Please try again later."
    mock_github_cls.assert_not_called()