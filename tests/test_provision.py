def test_manifest_build():
    from wasp.resources.platform import PlatformManifest

    manifest = PlatformManifest.build(
        name="wp2",
        domain="wasp.silvios.me",
        regions=["us-east-1", "sa-east-1"],
    )

    assert manifest.metadata.name == "wp2"
    assert manifest.spec.domain == "wasp.silvios.me"
    assert len(manifest.spec.regions) == 2
    r0 = manifest.spec.regions[0]
    assert r0.name == "us-east-1"
    assert r0.endpoint == "gateway.us-east-1.wp2.wasp.silvios.me"
    r1 = manifest.spec.regions[1]
    assert r1.endpoint == "gateway.sa-east-1.wp2.wasp.silvios.me"
    assert [s.name for s in manifest.spec.services] == [
        "auth",
        "discovery",
        "callback",
        "portal",
    ]


def test_manifest_yaml_output():
    import yaml
    from wasp.resources.platform import PlatformManifest

    manifest = PlatformManifest.build("wp2", "wasp.silvios.me", ["us-east-1"])
    yaml_str = yaml.dump(
        manifest.model_dump(), default_flow_style=False, sort_keys=False
    )
    data = yaml.safe_load(yaml_str)

    assert data["apiVersion"] == "wasp.silvios.me/v1alpha1"
    assert data["kind"] == "Platform"
    assert data["metadata"]["name"] == "wp2"
    assert data["spec"]["domain"] == "wasp.silvios.me"
    assert (
        data["spec"]["regions"][0]["endpoint"]
        == "gateway.us-east-1.wp2.wasp.silvios.me"
    )
    assert len(data["spec"]["services"]) == 4
    assert [s["name"] for s in data["spec"]["services"]] == [
        "auth",
        "discovery",
        "callback",
        "portal",
    ]


def test_provision_commits(monkeypatch):
    from unittest.mock import MagicMock
    from wasp.provision import provision_platform_instance

    mock_client_cls = MagicMock()
    mock_client = mock_client_cls.return_value

    monkeypatch.setenv("GH_PAT", "fake-pat")
    monkeypatch.setattr("wasp.gitops_committer.PyGithubClient", mock_client_cls)

    result = provision_platform_instance(
        name="wp2",
        domain="wasp.silvios.me",
        regions=["us-east-1"],
        requested_by="alice",
    )

    mock_client_cls.assert_called_once_with(
        pat="fake-pat", repo="smsilva/wasp-gitops", base_url="https://api.github.com"
    )
    call_kwargs = mock_client.create_file.call_args.kwargs
    assert call_kwargs["path"] == "infrastructure/tenants/wp2.yaml"
    assert call_kwargs["branch"] == "dev"
    assert "feat(tenants): provision wp2" in call_kwargs["message"]
    assert "Requested by: alice" in call_kwargs["message"]
    assert result["status"] == "provisioning"
    assert "wp2" in result["message"]


def test_provision_spawns_watcher(monkeypatch):
    import wasp.clients.telegram  # noqa: F401
    from unittest.mock import MagicMock, patch
    from wasp.provision import provision_platform_instance

    mock_client_cls = MagicMock()

    monkeypatch.setenv("GH_PAT", "x")
    monkeypatch.setenv("TELEGRAM_TOKEN", "tg-token")
    monkeypatch.setattr("wasp.gitops_committer.PyGithubClient", mock_client_cls)
    monkeypatch.setattr(
        "wasp.auth.is_authorized", lambda channel, channel_id: "user-abc"
    )

    mock_thread = MagicMock()
    mock_thread_cls = MagicMock(return_value=mock_thread)

    class FakeCtx:
        session_id = "tg:5621932873:5621932873"

    with patch("wasp.watcher.threading.Thread", mock_thread_cls):
        result = provision_platform_instance(
            name="wp2",
            domain="wasp.silvios.me",
            regions=["us-east-1"],
            run_context=FakeCtx(),
        )

    mock_thread_cls.assert_called_once()
    mock_thread.start.assert_called_once()
    assert result["status"] == "provisioning"


def test_provision_watcher_target_runs_asyncio(monkeypatch):
    import wasp.clients.telegram  # noqa: F401
    from unittest.mock import MagicMock, patch
    from wasp.provision import provision_platform_instance

    mock_client_cls = MagicMock()

    monkeypatch.setenv("GH_PAT", "x")
    monkeypatch.setenv("TELEGRAM_TOKEN", "tg-token")
    monkeypatch.setattr("wasp.gitops_committer.PyGithubClient", mock_client_cls)
    monkeypatch.setattr(
        "wasp.auth.is_authorized", lambda channel, channel_id: "user-abc"
    )

    mock_thread = MagicMock()
    mock_thread_cls = MagicMock(return_value=mock_thread)

    class FakeCtx:
        session_id = "tg:5621932873:5621932873"

    mock_watch = MagicMock()
    with (
        patch("wasp.watcher.threading.Thread", mock_thread_cls),
        patch("wasp.watcher.asyncio.run") as mock_asyncio_run,
        patch("wasp.watcher.watch_platform", mock_watch),
    ):
        provision_platform_instance(
            name="wp2",
            domain="wasp.silvios.me",
            regions=["us-east-1"],
            run_context=FakeCtx(),
        )
        target = mock_thread_cls.call_args.kwargs["target"]
        target()

    mock_asyncio_run.assert_called_once_with(mock_watch.return_value)


def test_provision_skips_watcher_without_chat_id(monkeypatch):
    from unittest.mock import MagicMock, patch
    from wasp.provision import provision_platform_instance

    mock_client_cls = MagicMock()

    monkeypatch.setenv("GH_PAT", "x")
    monkeypatch.setenv("TELEGRAM_TOKEN", "tg-token")
    monkeypatch.setattr("wasp.gitops_committer.PyGithubClient", mock_client_cls)

    mock_thread_cls = MagicMock()

    class FakeCtx:
        session_id = "web:abc:def"

    with patch("wasp.watcher.threading.Thread", mock_thread_cls):
        result = provision_platform_instance(
            name="wp2",
            domain="wasp.silvios.me",
            regions=["us-east-1"],
            run_context=FakeCtx(),
        )

    mock_thread_cls.assert_not_called()
    assert result["status"] == "provisioning"


def test_provision_creates_span(monkeypatch):
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
        InMemorySpanExporter,
    )
    import wasp.telemetry as telemetry

    exporter = InMemorySpanExporter()
    telemetry.configure(span_exporter=exporter)

    from unittest.mock import MagicMock

    mock_client_cls = MagicMock()

    monkeypatch.setenv("GH_PAT", "x")
    monkeypatch.setattr("wasp.gitops_committer.PyGithubClient", mock_client_cls)
    monkeypatch.setattr("wasp.watcher.threading.Thread", MagicMock())

    from wasp.provision import provision_platform_instance

    provision_platform_instance(name="wp-test")

    spans = exporter.get_finished_spans()
    assert any(s.name == "provision_platform_instance" for s in spans)


def test_provision_records_provisioning_started(monkeypatch):
    from opentelemetry.sdk.metrics.export import InMemoryMetricReader
    import wasp.telemetry as telemetry

    reader = InMemoryMetricReader()
    telemetry.configure(metric_reader=reader)

    from unittest.mock import MagicMock

    mock_client_cls = MagicMock()

    monkeypatch.setenv("GH_PAT", "x")
    monkeypatch.setattr("wasp.gitops_committer.PyGithubClient", mock_client_cls)
    monkeypatch.setattr("wasp.watcher.threading.Thread", MagicMock())

    from wasp.provision import provision_platform_instance

    provision_platform_instance(name="wp-test")

    metrics_data = reader.get_metrics_data()
    all_points = [
        dp
        for rm in metrics_data.resource_metrics
        for sm in rm.scope_metrics
        for m in sm.metrics
        if m.name == "agent.provisioning.total"
        for dp in m.data.data_points
    ]
    assert any(dp.attributes.get("outcome") == "started" for dp in all_points)


def test_provision_uses_custom_github_base_url(monkeypatch):
    from unittest.mock import MagicMock
    from wasp.provision import provision_platform_instance

    mock_client_cls = MagicMock()

    monkeypatch.setenv("GH_PAT", "fake-pat")
    monkeypatch.setenv("GITHUB_BASE_URL", "http://localhost:3000/api/v3")
    monkeypatch.setattr("wasp.gitops_committer.PyGithubClient", mock_client_cls)

    provision_platform_instance(name="wp2")

    mock_client_cls.assert_called_once_with(
        pat="fake-pat",
        repo="smsilva/wasp-gitops",
        base_url="http://localhost:3000/api/v3",
    )


def test_provision_uses_gitops_repo_env_var(monkeypatch):
    from unittest.mock import MagicMock
    from wasp.provision import provision_platform_instance

    mock_client_cls = MagicMock()

    monkeypatch.setenv("GH_PAT", "fake-pat")
    monkeypatch.setenv("GITOPS_REPO", "myorg/my-gitops")
    monkeypatch.setattr("wasp.gitops_committer.PyGithubClient", mock_client_cls)

    provision_platform_instance(name="wp2")

    mock_client_cls.assert_called_once_with(
        pat="fake-pat", repo="myorg/my-gitops", base_url="https://api.github.com"
    )


def test_provision_spawns_watcher_with_console_notifier(monkeypatch):
    from unittest.mock import MagicMock, patch
    from wasp.provision import provision_platform_instance

    mock_client_cls = MagicMock()

    monkeypatch.setenv("GH_PAT", "x")
    monkeypatch.delenv("TELEGRAM_TOKEN", raising=False)
    monkeypatch.setattr("wasp.gitops_committer.PyGithubClient", mock_client_cls)

    mock_thread = MagicMock()
    mock_thread_cls = MagicMock(return_value=mock_thread)

    class FakeCtx:
        session_id = "local:wasp-agent:abc12345"

    with patch("wasp.watcher.threading.Thread", mock_thread_cls):
        result = provision_platform_instance(
            name="wp2",
            domain="wasp.silvios.me",
            regions=["us-east-1"],
            run_context=FakeCtx(),
        )

    mock_thread_cls.assert_called_once()
    mock_thread.start.assert_called_once()
    assert result["status"] == "provisioning"


def test_provision_returns_already_provisioning_when_file_exists(monkeypatch):
    from unittest.mock import MagicMock, patch
    from wasp.git_client import FileAlreadyExistsError
    from wasp.provision import provision_platform_instance

    mock_client_cls = MagicMock()
    mock_client = mock_client_cls.return_value
    mock_client.create_file.side_effect = FileAlreadyExistsError(
        "infrastructure/tenants/wp2.yaml"
    )

    monkeypatch.setenv("GH_PAT", "fake-pat")
    monkeypatch.setattr("wasp.gitops_committer.PyGithubClient", mock_client_cls)
    monkeypatch.setattr(
        "wasp.auth.is_authorized", lambda channel, channel_id: "user-abc"
    )

    mock_thread_cls = MagicMock()

    class FakeCtx:
        session_id = "tg:5621932873:5621932873"

    with patch("wasp.watcher.threading.Thread", mock_thread_cls):
        result = provision_platform_instance(name="wp2", run_context=FakeCtx())

    assert result["status"] == "already_provisioning"
    assert "wp2" in result["message"]
    mock_thread_cls.assert_not_called()


def test_provision_returns_unauthorized_when_tg_chat_id_unknown(monkeypatch):
    from wasp.provision import provision_platform_instance

    monkeypatch.setattr("wasp.auth.is_authorized", lambda channel, channel_id: None)

    class FakeCtx:
        session_id = "tg:wasp-agent:999999"

    result = provision_platform_instance(
        name="x",
        domain="d",
        regions=["us-east-1"],
        run_context=FakeCtx(),
    )
    assert result == {"status": "unauthorized", "message": "Acesso negado."}


def test_provision_skips_auth_for_local_channel(monkeypatch):
    """local channel é trusted — não tem identidade verificável, boundary é a rede."""
    from unittest.mock import MagicMock, patch
    from wasp.provision import provision_platform_instance

    is_authorized_called = []
    monkeypatch.setattr(
        "wasp.auth.is_authorized",
        lambda c, i: is_authorized_called.append((c, i)) or None,
    )

    mock_client_cls = MagicMock()
    monkeypatch.setenv("GH_PAT", "x")
    monkeypatch.delenv("TELEGRAM_TOKEN", raising=False)
    monkeypatch.setattr("wasp.gitops_committer.PyGithubClient", mock_client_cls)

    class FakeCtx:
        session_id = "local:wasp-agent:abc12345"

    with patch("wasp.watcher.threading.Thread", MagicMock()):
        result = provision_platform_instance(
            name="x",
            domain="d",
            regions=["us-east-1"],
            run_context=FakeCtx(),
        )

    assert result["status"] == "provisioning"
    assert is_authorized_called == []


def test_provision_proceeds_when_tg_authorized(monkeypatch):
    import wasp.clients.telegram  # noqa: F401
    from unittest.mock import MagicMock, patch
    from wasp.provision import provision_platform_instance

    monkeypatch.setattr(
        "wasp.auth.is_authorized", lambda channel, channel_id: "user-abc"
    )

    mock_client_cls = MagicMock()
    monkeypatch.setenv("GH_PAT", "x")
    monkeypatch.setenv("TELEGRAM_TOKEN", "tg-token")
    monkeypatch.setattr("wasp.gitops_committer.PyGithubClient", mock_client_cls)

    mock_thread_cls = MagicMock()

    class FakeCtx:
        session_id = "tg:wasp-agent:5621932873"

    with patch("wasp.watcher.threading.Thread", mock_thread_cls):
        result = provision_platform_instance(
            name="wp2",
            domain="d",
            regions=["us-east-1"],
            run_context=FakeCtx(),
        )

    assert result["status"] == "provisioning"
    mock_thread_cls.assert_called_once()


def test_provision_sets_auth_channel_span_attribute_on_deny(monkeypatch):
    """Span attribute auth.channel is set even on auth deny."""
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
        InMemorySpanExporter,
    )
    import wasp.telemetry as telemetry

    exporter = InMemorySpanExporter()
    telemetry.configure(span_exporter=exporter)

    monkeypatch.setattr("wasp.auth.is_authorized", lambda c, i: None)

    from wasp.provision import provision_platform_instance

    class FakeCtx:
        session_id = "tg:wasp-agent:999999"

    result = provision_platform_instance(
        name="x",
        domain="d",
        regions=["us-east-1"],
        run_context=FakeCtx(),
    )
    assert result["status"] == "unauthorized"

    spans = exporter.get_finished_spans()
    span = next(s for s in spans if s.name == "provision_platform_instance")
    assert span.attributes.get("auth.channel") == "tg"


def test_provision_sets_user_id_span_attribute_when_authorized(monkeypatch):
    from unittest.mock import MagicMock, patch
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
        InMemorySpanExporter,
    )
    import wasp.telemetry as telemetry

    exporter = InMemorySpanExporter()
    telemetry.configure(span_exporter=exporter)

    monkeypatch.setattr("wasp.auth.is_authorized", lambda c, i: "user-abc")

    mock_client_cls = MagicMock()
    monkeypatch.setenv("GH_PAT", "x")
    monkeypatch.setenv("TELEGRAM_TOKEN", "tg-token")
    monkeypatch.setattr("wasp.gitops_committer.PyGithubClient", mock_client_cls)

    from wasp.provision import provision_platform_instance

    class FakeCtx:
        session_id = "tg:wasp-agent:111"

    with patch("wasp.watcher.threading.Thread", MagicMock()):
        provision_platform_instance(
            name="x",
            domain="d",
            regions=["us-east-1"],
            run_context=FakeCtx(),
        )

    spans = exporter.get_finished_spans()
    span = next(s for s in spans if s.name == "provision_platform_instance")
    assert span.attributes.get("user.id") == "user-abc"
    assert span.attributes.get("auth.channel") == "tg"


def test_provision_missing_pat(monkeypatch):
    from wasp.provision import provision_platform_instance

    monkeypatch.delenv("GH_PAT", raising=False)

    result = provision_platform_instance(name="wp2")

    assert result["status"] == "error"
    assert result["message"] == "Provisioning failed. Please try again later."


def test_list_returns_unauthorized_when_unknown_tg_chat_id(monkeypatch):
    from wasp.provision import list_platform_instances

    monkeypatch.setattr("wasp.auth.is_authorized", lambda c, i: None)

    class FakeCtx:
        session_id = "tg:wasp-agent:999"

    result = list_platform_instances(run_context=FakeCtx())

    assert result == {"status": "unauthorized", "message": "Acesso negado."}


def test_list_returns_tenants_with_status(monkeypatch):
    from unittest.mock import MagicMock
    from wasp.provision import list_platform_instances

    mock_api = MagicMock()
    mock_api.list_cluster_custom_object.return_value = {
        "items": [
            {
                "metadata": {"name": "acme"},
                "status": {"conditions": [{"type": "Ready", "status": "True"}]},
            },
            {
                "metadata": {"name": "globex"},
                "status": {"conditions": [{"type": "Ready", "status": "False"}]},
            },
            {"metadata": {"name": "fresh"}, "status": {}},
        ]
    }
    monkeypatch.setattr(
        "wasp.clients.k8s.reader.load_kube_config_auto", lambda: mock_api
    )

    class FakeCtx:
        session_id = "local:wasp-agent:abc"

    result = list_platform_instances(run_context=FakeCtx())

    assert result == {
        "status": "ok",
        "tenants": [
            {"name": "acme", "status": "Ready"},
            {"name": "globex", "status": "Pending"},
            {"name": "fresh", "status": "Unknown"},
        ],
    }


def test_list_returns_empty_list(monkeypatch):
    from unittest.mock import MagicMock
    from wasp.provision import list_platform_instances

    mock_api = MagicMock()
    mock_api.list_cluster_custom_object.return_value = {"items": []}
    monkeypatch.setattr(
        "wasp.clients.k8s.reader.load_kube_config_auto", lambda: mock_api
    )

    class FakeCtx:
        session_id = "local:wasp-agent:abc"

    result = list_platform_instances(run_context=FakeCtx())

    assert result == {"status": "ok", "tenants": []}


def test_list_returns_error_on_exception(monkeypatch):
    from unittest.mock import MagicMock
    from wasp.provision import list_platform_instances

    mock_api = MagicMock()
    mock_api.list_cluster_custom_object.side_effect = RuntimeError("boom")
    monkeypatch.setattr(
        "wasp.clients.k8s.reader.load_kube_config_auto", lambda: mock_api
    )

    class FakeCtx:
        session_id = "local:wasp-agent:abc"

    result = list_platform_instances(run_context=FakeCtx())

    assert result["status"] == "error"
    assert result["message"] == "List failed. Please try again later."


def test_list_creates_span(monkeypatch):
    from unittest.mock import MagicMock
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
        InMemorySpanExporter,
    )
    import wasp.telemetry as telemetry

    exporter = InMemorySpanExporter()
    telemetry.configure(span_exporter=exporter)

    mock_api = MagicMock()
    mock_api.list_cluster_custom_object.return_value = {"items": []}
    monkeypatch.setattr(
        "wasp.clients.k8s.reader.load_kube_config_auto", lambda: mock_api
    )

    from wasp.provision import list_platform_instances

    list_platform_instances()

    spans = exporter.get_finished_spans()
    assert any(s.name == "list_platform_instances" for s in spans)


def test_provision_defaults_requested_by_to_user_id(monkeypatch):
    from unittest.mock import MagicMock, patch
    from wasp.provision import provision_platform_instance

    mock_client_cls = MagicMock()
    mock_client = mock_client_cls.return_value

    monkeypatch.setenv("GH_PAT", "fake-pat")
    monkeypatch.setenv("TELEGRAM_TOKEN", "tg-token")
    monkeypatch.setattr("wasp.gitops_committer.PyGithubClient", mock_client_cls)
    monkeypatch.setattr(
        "wasp.auth.is_authorized", lambda channel, channel_id: "user-abc"
    )

    class FakeCtx:
        session_id = "tg:wasp-agent:5621932873"

    with patch("wasp.watcher.threading.Thread", MagicMock()):
        provision_platform_instance(
            name="wp2",
            domain="wasp.silvios.me",
            regions=["us-east-1"],
            run_context=FakeCtx(),
        )

    msg = mock_client.create_file.call_args.kwargs["message"]
    assert "Requested by: user-abc" in msg


def test_provision_defaults_requested_by_to_local_operator(monkeypatch):
    from unittest.mock import MagicMock, patch
    from wasp.provision import provision_platform_instance

    mock_client_cls = MagicMock()
    mock_client = mock_client_cls.return_value

    monkeypatch.setenv("GH_PAT", "fake-pat")
    monkeypatch.delenv("TELEGRAM_TOKEN", raising=False)
    monkeypatch.setattr("wasp.gitops_committer.PyGithubClient", mock_client_cls)

    class FakeCtx:
        session_id = "local:wasp-agent:abc12345"

    with patch("wasp.watcher.threading.Thread", MagicMock()):
        provision_platform_instance(
            name="wp2",
            domain="wasp.silvios.me",
            regions=["us-east-1"],
            run_context=FakeCtx(),
        )

    msg = mock_client.create_file.call_args.kwargs["message"]
    assert "Requested by: local-operator" in msg


def test_provision_defaults_requested_by_to_unknown_without_context(monkeypatch):
    from unittest.mock import MagicMock
    from wasp.provision import provision_platform_instance

    mock_client_cls = MagicMock()
    mock_client = mock_client_cls.return_value

    monkeypatch.setenv("GH_PAT", "fake-pat")
    monkeypatch.setattr("wasp.gitops_committer.PyGithubClient", mock_client_cls)
    monkeypatch.setattr("wasp.watcher.threading.Thread", MagicMock())

    provision_platform_instance(name="wp2")

    msg = mock_client.create_file.call_args.kwargs["message"]
    assert "Requested by: unknown" in msg
