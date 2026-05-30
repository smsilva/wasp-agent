from unittest.mock import MagicMock


def test_guard_returns_none_when_no_channel():
    from wasp.auth_guard import AuthorizationGuard

    span = MagicMock()
    user_id, err = AuthorizationGuard().check(channel=None, chat_id=None, span=span)

    assert user_id is None
    assert err is None
    span.set_attribute.assert_not_called()


def test_guard_returns_local_operator_for_trusted_channel():
    from wasp.auth_guard import AuthorizationGuard

    span = MagicMock()
    user_id, err = AuthorizationGuard().check(channel="local", chat_id="abc", span=span)

    assert user_id == "local-operator"
    assert err is None
    span.set_attribute.assert_any_call("auth.channel", "local")
    span.set_attribute.assert_any_call("user.id", "local-operator")


def test_guard_authorizes_known_tg_user(monkeypatch):
    from wasp.auth_guard import AuthorizationGuard
    from wasp import auth

    monkeypatch.setattr(auth.get_repository(), "is_authorized", lambda c, i: "user-abc")
    span = MagicMock()
    user_id, err = AuthorizationGuard().check(channel="tg", chat_id="111", span=span)

    assert user_id == "user-abc"
    assert err is None
    span.set_attribute.assert_any_call("auth.channel", "tg")
    span.set_attribute.assert_any_call("user.id", "user-abc")


def test_guard_denies_unknown_tg_user(monkeypatch):
    from wasp.auth_guard import AuthorizationGuard
    import wasp.telemetry as telemetry
    from wasp import auth

    monkeypatch.setattr(auth.get_repository(), "is_authorized", lambda c, i: None)
    auth_denied_calls = []
    monkeypatch.setattr(
        telemetry, "auth_denied", lambda **kw: auth_denied_calls.append(kw)
    )

    span = MagicMock()
    user_id, err = AuthorizationGuard().check(channel="tg", chat_id="999", span=span)

    assert user_id is None
    assert err == {"status": "unauthorized", "message": "Acesso negado."}
    assert auth_denied_calls == [{"channel": "tg", "reason": "unknown_identity"}]
    span.set_attribute.assert_any_call("auth.channel", "tg")


def test_guard_denies_when_chat_id_missing(monkeypatch):
    from wasp.auth_guard import AuthorizationGuard
    import wasp.telemetry as telemetry
    from wasp import auth

    called = []
    monkeypatch.setattr(
        auth.get_repository(),
        "is_authorized",
        lambda c, i: called.append((c, i)) or "user-abc",
    )
    monkeypatch.setattr(telemetry, "auth_denied", lambda **kw: None)

    span = MagicMock()
    user_id, err = AuthorizationGuard().check(channel="tg", chat_id=None, span=span)

    assert user_id is None
    assert err == {"status": "unauthorized", "message": "Acesso negado."}
    assert called == []
