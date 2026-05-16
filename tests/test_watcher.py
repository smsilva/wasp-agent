def test_extract_chat_id_from_telegram_session():
    from tools.watcher import extract_chat_id

    class FakeCtx:
        session_id = "tg:5621932873:5621932873"

    assert extract_chat_id(FakeCtx()) == "5621932873"


def test_extract_chat_id_returns_none_for_non_telegram():
    from tools.watcher import extract_chat_id

    class FakeCtx:
        session_id = "web:abc:def"

    class EmptyCtx:
        session_id = ""

    assert extract_chat_id(FakeCtx()) is None
    assert extract_chat_id(None) is None
    assert extract_chat_id(EmptyCtx()) is None


def test_ready_message_includes_endpoints():
    from tools.watcher import ready_message

    platform = {
        "spec": {
            "regions": [
                {"name": "us-east-1", "endpoint": "gateway.us-east-1.wp2.wasp.silvios.me"},
                {"name": "sa-east-1", "endpoint": "gateway.sa-east-1.wp2.wasp.silvios.me"},
            ]
        }
    }
    msg = ready_message("wp2", platform)
    assert "wp2" in msg
    assert "us-east-1" in msg
    assert "https://gateway.us-east-1.wp2.wasp.silvios.me" in msg
    assert "https://gateway.sa-east-1.wp2.wasp.silvios.me" in msg


def test_load_kube_config_auto_incluster(monkeypatch):
    from unittest.mock import MagicMock
    import tools.watcher as w

    incluster = MagicMock()
    local = MagicMock()
    monkeypatch.setattr(w.config, "load_incluster_config", incluster)
    monkeypatch.setattr(w.config, "load_kube_config", local)

    w.load_kube_config_auto()

    incluster.assert_called_once()
    local.assert_not_called()


def test_load_kube_config_auto_fallback_local(monkeypatch):
    from unittest.mock import MagicMock
    import tools.watcher as w

    class FakeConfigException(Exception):
        pass

    # ConfigException must be a real Exception subclass for raise/except to work with mocked module
    monkeypatch.setattr(w.config, "ConfigException", FakeConfigException)

    def raise_(*a, **kw):
        raise FakeConfigException("not in cluster")

    incluster = MagicMock(side_effect=raise_)
    local = MagicMock()
    monkeypatch.setattr(w.config, "load_incluster_config", incluster)
    monkeypatch.setattr(w.config, "load_kube_config", local)

    w.load_kube_config_auto()

    incluster.assert_called_once()
    local.assert_called_once()
