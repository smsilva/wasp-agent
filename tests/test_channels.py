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
