from unittest.mock import MagicMock


def test_provisioner_commits_to_clusters_path(monkeypatch):
    from wasp.resources.cluster.provisioner import ClusterProvisioner

    monkeypatch.setenv("GH_PAT", "x")
    monkeypatch.setenv("GITOPS_REPO", "myorg/my-gitops")
    monkeypatch.setenv("GITHUB_BASE_URL", "https://api.github.com")
    mock_client_cls = MagicMock()
    mock_client = mock_client_cls.return_value
    monkeypatch.setattr("wasp.gitops_committer.PyGithubClient", mock_client_cls)

    guard = MagicMock()
    guard.check.return_value = ("local-operator", None)
    spawner = MagicMock()
    spawner.spawn.return_value = False

    class FakeCtx:
        session_id = "local:wasp-agent:abc"

    result = ClusterProvisioner(guard=guard, watcher_spawner=spawner).provision(
        name="edge",
        kubernetes_version="1.34",
        requested_by="alice",
        run_context=FakeCtx(),
    )

    call_kwargs = mock_client.create_file.call_args.kwargs
    assert call_kwargs["path"] == "infrastructure/clusters/edge.yaml"
    assert "feat(clusters): provision edge" in call_kwargs["message"]
    assert "Requested by: alice" in call_kwargs["message"]
    assert result["status"] == "provisioning"
    assert "edge" in result["message"]


def test_provisioner_rewrites_already_provisioning_message(monkeypatch):
    from wasp.git_client import FileAlreadyExistsError
    from wasp.resources.cluster.provisioner import ClusterProvisioner

    monkeypatch.setenv("GH_PAT", "x")
    monkeypatch.setenv("GITOPS_REPO", "myorg/my-gitops")
    monkeypatch.setenv("GITHUB_BASE_URL", "https://api.github.com")
    mock_client_cls = MagicMock()
    mock_client = mock_client_cls.return_value
    mock_client.create_file.side_effect = FileAlreadyExistsError(
        "infrastructure/clusters/edge.yaml"
    )
    monkeypatch.setattr("wasp.gitops_committer.PyGithubClient", mock_client_cls)

    guard = MagicMock()
    guard.check.return_value = ("local-operator", None)
    spawner = MagicMock()

    class FakeCtx:
        session_id = "local:wasp-agent:abc"

    result = ClusterProvisioner(guard=guard, watcher_spawner=spawner).provision(
        name="edge",
        kubernetes_version="1.34",
        requested_by="alice",
        run_context=FakeCtx(),
    )

    assert result["status"] == "already_provisioning"
    assert "Cluster 'edge'" in result["message"]
    spawner.spawn.assert_not_called()


def test_provisioner_returns_unauthorized_when_guard_denies():
    from wasp.resources.cluster.provisioner import ClusterProvisioner

    guard = MagicMock()
    guard.check.return_value = (
        None,
        {"status": "unauthorized", "message": "Acesso negado."},
    )
    spawner = MagicMock()

    class FakeCtx:
        session_id = "tg:wasp-agent:999"

    result = ClusterProvisioner(guard=guard, watcher_spawner=spawner).provision(
        name="edge",
        kubernetes_version="1.34",
        requested_by="",
        run_context=FakeCtx(),
    )

    assert result == {"status": "unauthorized", "message": "Acesso negado."}


def test_provisioner_returns_error_on_exception(monkeypatch):
    from wasp.resources.cluster.provisioner import ClusterProvisioner

    monkeypatch.delenv("GH_PAT", raising=False)
    guard = MagicMock()
    guard.check.return_value = ("local-operator", None)
    spawner = MagicMock()

    class FakeCtx:
        session_id = "local:wasp-agent:abc"

    result = ClusterProvisioner(guard=guard, watcher_spawner=spawner).provision(
        name="edge",
        kubernetes_version="1.34",
        requested_by="",
        run_context=FakeCtx(),
    )

    assert result["status"] == "error"
    assert result["message"] == "Provisioning failed. Please try again later."