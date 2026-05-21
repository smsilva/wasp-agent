def test_manifest_build():
    from wasp.provision import PlatformManifest

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
        "auth", "discovery", "callback", "portal"
    ]


def test_manifest_yaml_output():
    import yaml
    from wasp.provision import PlatformManifest

    manifest = PlatformManifest.build("wp2", "wasp.silvios.me", ["us-east-1"])
    yaml_str = yaml.dump(manifest.model_dump(), default_flow_style=False, sort_keys=False)
    data = yaml.safe_load(yaml_str)

    assert data["apiVersion"] == "wasp.silvios.me/v1alpha1"
    assert data["kind"] == "Platform"
    assert data["metadata"]["name"] == "wp2"
    assert data["spec"]["domain"] == "wasp.silvios.me"
    assert data["spec"]["regions"][0]["endpoint"] == "gateway.us-east-1.wp2.wasp.silvios.me"
    assert len(data["spec"]["services"]) == 4
    assert [s["name"] for s in data["spec"]["services"]] == [
        "auth", "discovery", "callback", "portal"
    ]


def test_provision_commits(monkeypatch):
    from unittest.mock import MagicMock
    from wasp.provision import provision_platform_instance

    mock_client_cls = MagicMock()
    mock_client = mock_client_cls.return_value

    monkeypatch.setenv("GH_PAT", "fake-pat")
    monkeypatch.setattr("wasp.provision.PyGithubClient", mock_client_cls)

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
    from unittest.mock import MagicMock, patch
    from wasp.provision import provision_platform_instance

    mock_client_cls = MagicMock()

    monkeypatch.setenv("GH_PAT", "x")
    monkeypatch.setenv("TELEGRAM_TOKEN", "tg-token")
    monkeypatch.setattr("wasp.provision.PyGithubClient", mock_client_cls)

    mock_thread = MagicMock()
    mock_thread_cls = MagicMock(return_value=mock_thread)

    class FakeCtx:
        session_id = "tg:5621932873:5621932873"

    with patch("wasp.provision.threading.Thread", mock_thread_cls):
        result = provision_platform_instance(
            name="wp2", domain="wasp.silvios.me", regions=["us-east-1"], run_context=FakeCtx(),
        )

    mock_thread_cls.assert_called_once()
    mock_thread.start.assert_called_once()
    assert result["status"] == "provisioning"


def test_provision_watcher_target_runs_asyncio(monkeypatch):
    from unittest.mock import MagicMock, patch
    from wasp.provision import provision_platform_instance

    mock_client_cls = MagicMock()

    monkeypatch.setenv("GH_PAT", "x")
    monkeypatch.setenv("TELEGRAM_TOKEN", "tg-token")
    monkeypatch.setattr("wasp.provision.PyGithubClient", mock_client_cls)

    mock_thread = MagicMock()
    mock_thread_cls = MagicMock(return_value=mock_thread)

    class FakeCtx:
        session_id = "tg:5621932873:5621932873"

    mock_watch = MagicMock()
    with patch("wasp.provision.threading.Thread", mock_thread_cls), \
         patch("wasp.provision.asyncio.run") as mock_asyncio_run, \
         patch("wasp.provision.watch_platform", mock_watch):
        provision_platform_instance(
            name="wp2", domain="wasp.silvios.me", regions=["us-east-1"], run_context=FakeCtx(),
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
    monkeypatch.setattr("wasp.provision.PyGithubClient", mock_client_cls)

    mock_thread_cls = MagicMock()

    class FakeCtx:
        session_id = "web:abc:def"

    with patch("wasp.provision.threading.Thread", mock_thread_cls):
        result = provision_platform_instance(
            name="wp2", domain="wasp.silvios.me", regions=["us-east-1"], run_context=FakeCtx(),
        )

    mock_thread_cls.assert_not_called()
    assert result["status"] == "provisioning"


def test_provision_creates_span(monkeypatch):
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
    import wasp.telemetry as telemetry
    exporter = InMemorySpanExporter()
    telemetry.configure(span_exporter=exporter)

    from unittest.mock import MagicMock
    mock_client_cls = MagicMock()

    monkeypatch.setenv("GH_PAT", "x")
    monkeypatch.setattr("wasp.provision.PyGithubClient", mock_client_cls)
    monkeypatch.setattr("wasp.provision.threading.Thread", MagicMock())

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
    monkeypatch.setattr("wasp.provision.PyGithubClient", mock_client_cls)
    monkeypatch.setattr("wasp.provision.threading.Thread", MagicMock())

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
    monkeypatch.setattr("wasp.provision.PyGithubClient", mock_client_cls)

    provision_platform_instance(name="wp2")

    mock_client_cls.assert_called_once_with(
        pat="fake-pat", repo="smsilva/wasp-gitops", base_url="http://localhost:3000/api/v3"
    )


def test_provision_uses_gitops_repo_env_var(monkeypatch):
    from unittest.mock import MagicMock
    from wasp.provision import provision_platform_instance

    mock_client_cls = MagicMock()

    monkeypatch.setenv("GH_PAT", "fake-pat")
    monkeypatch.setenv("GITOPS_REPO", "myorg/my-gitops")
    monkeypatch.setattr("wasp.provision.PyGithubClient", mock_client_cls)

    provision_platform_instance(name="wp2")

    mock_client_cls.assert_called_once_with(
        pat="fake-pat", repo="myorg/my-gitops", base_url="https://api.github.com"
    )


def test_select_notifier_console_when_env_explicit(monkeypatch):
    from wasp.provision import _select_notifier
    from wasp.notifier import ConsoleNotifier

    monkeypatch.setenv("WASP_AGENT_NOTIFIER", "console")
    monkeypatch.setenv("TELEGRAM_TOKEN", "tg-token")

    notifier = _select_notifier()
    assert isinstance(notifier, ConsoleNotifier)


def test_select_notifier_telegram_when_env_explicit(monkeypatch):
    from wasp.provision import _select_notifier
    from wasp.notifier import TelegramNotifier

    monkeypatch.setenv("WASP_AGENT_NOTIFIER", "telegram")
    monkeypatch.setenv("TELEGRAM_TOKEN", "tg-token")

    notifier = _select_notifier()
    assert isinstance(notifier, TelegramNotifier)


def test_select_notifier_default_telegram_when_token(monkeypatch):
    from wasp.provision import _select_notifier
    from wasp.notifier import TelegramNotifier

    monkeypatch.delenv("WASP_AGENT_NOTIFIER", raising=False)
    monkeypatch.setenv("TELEGRAM_TOKEN", "tg-token")

    notifier = _select_notifier()
    assert isinstance(notifier, TelegramNotifier)


def test_select_notifier_default_console_without_token(monkeypatch):
    from wasp.provision import _select_notifier
    from wasp.notifier import ConsoleNotifier

    monkeypatch.delenv("WASP_AGENT_NOTIFIER", raising=False)
    monkeypatch.delenv("TELEGRAM_TOKEN", raising=False)

    notifier = _select_notifier()
    assert isinstance(notifier, ConsoleNotifier)


def test_select_notifier_returns_none_when_telegram_without_token(monkeypatch):
    from wasp.provision import _select_notifier

    monkeypatch.setenv("WASP_AGENT_NOTIFIER", "telegram")
    monkeypatch.delenv("TELEGRAM_TOKEN", raising=False)

    assert _select_notifier() is None


def test_select_notifier_returns_none_for_unknown_kind(monkeypatch):
    from wasp.provision import _select_notifier

    monkeypatch.setenv("WASP_AGENT_NOTIFIER", "discord")
    assert _select_notifier() is None


def test_select_notifier_local_channel_picks_console_even_with_telegram_token(monkeypatch):
    from wasp.provision import _select_notifier
    from wasp.notifier import ConsoleNotifier

    monkeypatch.delenv("WASP_AGENT_NOTIFIER", raising=False)
    monkeypatch.setenv("TELEGRAM_TOKEN", "tg-token")

    notifier = _select_notifier(channel="local")
    assert isinstance(notifier, ConsoleNotifier)


def test_select_notifier_tg_channel_picks_telegram(monkeypatch):
    from wasp.provision import _select_notifier
    from wasp.notifier import TelegramNotifier

    monkeypatch.delenv("WASP_AGENT_NOTIFIER", raising=False)
    monkeypatch.setenv("TELEGRAM_TOKEN", "tg-token")

    notifier = _select_notifier(channel="tg")
    assert isinstance(notifier, TelegramNotifier)


def test_select_notifier_env_overrides_channel(monkeypatch):
    from wasp.provision import _select_notifier
    from wasp.notifier import ConsoleNotifier

    monkeypatch.setenv("WASP_AGENT_NOTIFIER", "console")
    monkeypatch.setenv("TELEGRAM_TOKEN", "tg-token")

    notifier = _select_notifier(channel="tg")
    assert isinstance(notifier, ConsoleNotifier)


def test_provision_spawns_watcher_with_console_notifier(monkeypatch):
    from unittest.mock import MagicMock, patch
    from wasp.provision import provision_platform_instance

    mock_client_cls = MagicMock()

    monkeypatch.setenv("GH_PAT", "x")
    monkeypatch.delenv("TELEGRAM_TOKEN", raising=False)
    monkeypatch.setattr("wasp.provision.PyGithubClient", mock_client_cls)

    mock_thread = MagicMock()
    mock_thread_cls = MagicMock(return_value=mock_thread)

    class FakeCtx:
        session_id = "local:wasp-agent:abc12345"

    with patch("wasp.provision.threading.Thread", mock_thread_cls):
        result = provision_platform_instance(
            name="wp2", domain="wasp.silvios.me", regions=["us-east-1"], run_context=FakeCtx(),
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
    monkeypatch.setattr("wasp.provision.PyGithubClient", mock_client_cls)

    mock_thread_cls = MagicMock()

    class FakeCtx:
        session_id = "tg:5621932873:5621932873"

    with patch("wasp.provision.threading.Thread", mock_thread_cls):
        result = provision_platform_instance(name="wp2", run_context=FakeCtx())

    assert result["status"] == "already_provisioning"
    assert "wp2" in result["message"]
    mock_thread_cls.assert_not_called()


def test_provision_missing_pat(monkeypatch):
    from unittest.mock import MagicMock
    from wasp.provision import provision_platform_instance

    monkeypatch.delenv("GH_PAT", raising=False)
    mock_client_cls = MagicMock()
    monkeypatch.setattr("wasp.provision.PyGithubClient", mock_client_cls)

    result = provision_platform_instance(name="wp2")

    assert result["status"] == "error"
    assert result["message"] == "Provisioning failed. Please try again later."
    mock_client_cls.assert_not_called()
