import pytest

from wasp import auth, auth_cli


@pytest.fixture(autouse=True)
def _db_isolation(tmp_path, monkeypatch):
    monkeypatch.setenv("WASP_AGENT_DB_FILE", str(tmp_path / "agent.db"))
    auth._reset_repository()
    yield
    auth._reset_repository()


def test_invite_prints_token_returns_zero(capsys):
    rc = auth_cli.main(["invite", "--name", "Alice", "--created-by", "admin"])
    assert rc == 0
    out = capsys.readouterr().out.strip()
    assert out  # non-empty token
    # Token must be redeemable.
    result = auth.get_repository().redeem_invite(out, "tg", "111")
    assert result is not None
    assert result[1] == "Alice"


def test_invite_with_channel(capsys):
    rc = auth_cli.main(
        ["invite", "--name", "Bob", "--created-by", "admin", "--channel", "tg"]
    )
    assert rc == 0
    token = capsys.readouterr().out.strip()
    # Bound to channel "tg" — redeem on "local" must fail.
    assert auth.get_repository().redeem_invite(token, "local", "1") is None
    assert auth.get_repository().redeem_invite(token, "tg", "222") is not None


def test_revoke_not_found_returns_one(capsys):
    rc = auth_cli.main(["revoke", "--channel", "tg", "--channel-id", "111"])
    assert rc == 1
    captured = capsys.readouterr()
    assert "not found" in captured.err


def test_revoke_after_linking_returns_zero(capsys):
    token = auth.get_repository().create_invite(
        display_name="Carol", created_by="admin"
    )
    auth.get_repository().redeem_invite(token, "tg", "333")

    rc = auth_cli.main(["revoke", "--channel", "tg", "--channel-id", "333"])
    assert rc == 0
    assert capsys.readouterr().out.strip() == "revoked"
    assert auth.get_repository().is_authorized("tg", "333") is None


def test_list_empty(capsys):
    rc = auth_cli.main(["list"])
    assert rc == 0
    assert capsys.readouterr().out.strip() == "(no identities)"


def test_bootstrap_creates_first_user(capsys):
    rc = auth_cli.main(
        ["bootstrap", "--name", "Silvio", "--channel", "tg", "--channel-id", "12345678"]
    )
    assert rc == 0
    user_id = capsys.readouterr().out.strip()
    assert user_id
    assert auth.get_repository().is_authorized("tg", "12345678") == user_id


def test_bootstrap_fails_when_db_not_empty(capsys):
    auth.get_repository().create_user("First")
    rc = auth_cli.main(
        ["bootstrap", "--name", "Silvio", "--channel", "tg", "--channel-id", "12345678"]
    )
    assert rc == 1
    captured = capsys.readouterr()
    assert "not empty" in captured.err


def test_link_adds_identity_to_existing_user(capsys):
    user_id = auth.get_repository().create_user("Silvio")
    rc = auth_cli.main(
        [
            "link",
            "--user-id",
            user_id,
            "--channel",
            "dc",
            "--channel-id",
            "708384119989600337",
        ]
    )
    assert rc == 0
    assert capsys.readouterr().out.strip() == "linked"
    assert auth.get_repository().is_authorized("dc", "708384119989600337") == user_id


def test_link_fails_on_duplicate_identity(capsys):
    user_id = auth.get_repository().create_user("Silvio")
    auth.get_repository().link_identity(user_id, "dc", "111")
    rc = auth_cli.main(
        ["link", "--user-id", user_id, "--channel", "dc", "--channel-id", "111"]
    )
    assert rc == 1


def test_list_prints_table(capsys):
    token = auth.get_repository().create_invite(display_name="Dave", created_by="admin")
    auth.get_repository().redeem_invite(token, "tg", "444")

    rc = auth_cli.main(["list"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "channel" in out
    assert "channel_id" in out
    assert "tg" in out
    assert "444" in out
    assert "Dave" in out
