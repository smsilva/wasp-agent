import pytest
from unittest.mock import MagicMock


@pytest.fixture(autouse=True)
def _reset_channels():
    from wasp.clients import channels
    channels.reset()
    yield
    channels.reset()


def test_register_and_get_returns_channel():
    from wasp.clients import channels

    ch = MagicMock(name="ch")
    ch.name = "fake"
    channels.register(ch)
    assert channels.get("fake") is ch


def test_get_returns_none_for_unknown_name():
    from wasp.clients import channels

    assert channels.get("missing") is None


def test_iter_channels_yields_registered_channels():
    from wasp.clients import channels

    a = MagicMock()
    a.name = "a"
    b = MagicMock()
    b.name = "b"
    channels.register(a)
    channels.register(b)
    assert set(channels.iter_channels()) == {a, b}


def test_register_overwrites_same_name():
    from wasp.clients import channels

    a = MagicMock()
    a.name = "x"
    b = MagicMock()
    b.name = "x"
    channels.register(a)
    channels.register(b)
    assert channels.get("x") is b
    assert list(channels.iter_channels()) == [b]


def test_reset_clears_registry():
    from wasp.clients import channels

    ch = MagicMock()
    ch.name = "x"
    channels.register(ch)
    channels.reset()
    assert channels.get("x") is None
    assert list(channels.iter_channels()) == []


def _fake_channel(name, *, enabled=True, interface=None, lifespan_cm=None, notifier=None):
    ch = MagicMock()
    ch.name = name
    ch.enabled = MagicMock(return_value=enabled)
    ch.build_interface = MagicMock(return_value=interface)
    ch.lifespan = MagicMock(return_value=lifespan_cm)
    ch.notifier = MagicMock(return_value=notifier)
    return ch


def test_build_app_collects_interfaces_from_enabled_channels(mock_agno):
    from wasp.clients import channels
    from wasp.clients.channels import ChannelLoader

    iface_a = MagicMock(name="iface_a")
    iface_b = MagicMock(name="iface_b")
    channels.register(_fake_channel("a", interface=iface_a))
    channels.register(_fake_channel("b", interface=iface_b))
    channels.register(_fake_channel("c", enabled=False, interface=MagicMock()))

    agent = MagicMock()
    ChannelLoader(agent).build_app()

    agent_os_kwargs = mock_agno["agno.os"].AgentOS.call_args.kwargs
    assert agent_os_kwargs["agents"] == [agent]
    assert set(agent_os_kwargs["interfaces"]) == {iface_a, iface_b}


def test_build_app_returns_app_and_agent_os(mock_agno):
    from wasp.clients.channels import ChannelLoader

    app, agent_os = ChannelLoader(MagicMock()).build_app()

    agent_os_mock = mock_agno["agno.os"].AgentOS.return_value
    assert app is agent_os_mock.get_app.return_value
    assert agent_os is agent_os_mock


def test_build_app_registers_prometheus_route(mock_agno, monkeypatch):
    import wasp.telemetry as telemetry
    from wasp.clients.channels import ChannelLoader

    spy = MagicMock()
    monkeypatch.setattr(telemetry, "register_prometheus_route", spy)

    app, _ = ChannelLoader(MagicMock()).build_app()
    spy.assert_called_once_with(app)


def test_build_app_skips_channels_with_none_interface(mock_agno):
    from wasp.clients import channels
    from wasp.clients.channels import ChannelLoader

    channels.register(_fake_channel("no-iface", interface=None))
    ChannelLoader(MagicMock()).build_app()

    agent_os_kwargs = mock_agno["agno.os"].AgentOS.call_args.kwargs
    assert agent_os_kwargs["interfaces"] == []


def test_build_app_ignores_disabled_channels(mock_agno):
    from wasp.clients import channels
    from wasp.clients.channels import ChannelLoader

    disabled = _fake_channel("off", enabled=False, interface=MagicMock())
    channels.register(disabled)
    ChannelLoader(MagicMock()).build_app()

    disabled.build_interface.assert_not_called()
    agent_os_kwargs = mock_agno["agno.os"].AgentOS.call_args.kwargs
    assert agent_os_kwargs["interfaces"] == []
