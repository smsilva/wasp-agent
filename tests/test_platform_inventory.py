from unittest.mock import MagicMock


def test_status_from_conditions_ready():
    from wasp.resources.platform.inventory import _status_from_conditions

    platform = {"status": {"conditions": [{"type": "Ready", "status": "True"}]}}
    assert _status_from_conditions(platform) == "Ready"


def test_status_from_conditions_pending():
    from wasp.resources.platform.inventory import _status_from_conditions

    platform = {"status": {"conditions": [{"type": "Ready", "status": "False"}]}}
    assert _status_from_conditions(platform) == "Pending"


def test_status_from_conditions_unknown_when_missing():
    from wasp.resources.platform.inventory import _status_from_conditions

    assert _status_from_conditions({"status": {"conditions": []}}) == "Unknown"
    assert _status_from_conditions({}) == "Unknown"


def test_inventory_list_transforms_items():
    from wasp.resources.platform.inventory import PlatformInventory

    reader = MagicMock()
    reader.search_for_instance_of.return_value = [
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
    guard = MagicMock()
    guard.check.return_value = ("local-operator", None)

    class FakeCtx:
        session_id = "local:wasp-agent:abc"

    result = PlatformInventory(guard=guard, reader=reader).list(FakeCtx())

    assert result == {
        "status": "ok",
        "tenants": [
            {"name": "acme", "status": "Ready"},
            {"name": "globex", "status": "Pending"},
            {"name": "fresh", "status": "Unknown"},
        ],
    }


def test_inventory_list_calls_reader_with_platform_gvp():
    from wasp.resources.platform.inventory import PlatformInventory
    from wasp.resources.platform.manifest import (
        PLATFORM_GROUP,
        PLATFORM_PLURAL,
        PLATFORM_VERSION,
    )

    reader = MagicMock()
    reader.search_for_instance_of.return_value = []
    guard = MagicMock()
    guard.check.return_value = ("local-operator", None)

    class FakeCtx:
        session_id = "local:wasp-agent:abc"

    PlatformInventory(guard=guard, reader=reader).list(FakeCtx())

    reader.search_for_instance_of.assert_called_once_with(
        PLATFORM_GROUP, PLATFORM_VERSION, PLATFORM_PLURAL
    )


def test_inventory_list_returns_unauthorized_when_guard_denies():
    from wasp.resources.platform.inventory import PlatformInventory

    reader = MagicMock()
    guard = MagicMock()
    guard.check.return_value = (
        None,
        {"status": "unauthorized", "message": "Acesso negado."},
    )

    class FakeCtx:
        session_id = "tg:wasp-agent:999"

    result = PlatformInventory(guard=guard, reader=reader).list(FakeCtx())

    assert result == {"status": "unauthorized", "message": "Acesso negado."}
    reader.search_for_instance_of.assert_not_called()


def test_inventory_list_returns_error_on_exception():
    from wasp.resources.platform.inventory import PlatformInventory

    reader = MagicMock()
    reader.search_for_instance_of.side_effect = RuntimeError("boom")
    guard = MagicMock()
    guard.check.return_value = ("local-operator", None)

    class FakeCtx:
        session_id = "local:wasp-agent:abc"

    result = PlatformInventory(guard=guard, reader=reader).list(FakeCtx())

    assert result["status"] == "error"
    assert result["message"] == "List failed. Please try again later."


def test_inventory_get_returns_message_when_ready():
    from wasp.resources.platform.inventory import PlatformInventory

    reader = MagicMock()
    reader.get_by_name.return_value = {
        "metadata": {"name": "acme"},
        "status": {
            "conditions": [
                {
                    "type": "Ready",
                    "status": "True",
                    "lastTransitionTime": "2026-05-30T10:00:00Z",
                }
            ]
        },
    }
    guard = MagicMock()
    guard.check.return_value = ("local-operator", None)

    class FakeCtx:
        session_id = "local:wasp-agent:abc"

    result = PlatformInventory(guard=guard, reader=reader).get("acme", FakeCtx())

    assert result["status"] == "Ready"
    assert result["name"] == "acme"
    assert result["message"] == "A Platform acme está Ready desde 30/05."


def test_inventory_get_returns_message_when_not_found():
    from wasp.resources.platform.inventory import PlatformInventory

    reader = MagicMock()
    reader.get_by_name.return_value = None
    guard = MagicMock()
    guard.check.return_value = ("local-operator", None)

    class FakeCtx:
        session_id = "local:wasp-agent:abc"

    result = PlatformInventory(guard=guard, reader=reader).get("ghost", FakeCtx())

    assert result["status"] == "not_found"
    assert result["name"] == "ghost"
    assert "ghost" in result["message"]


def test_inventory_get_returns_unauthorized_when_guard_denies():
    from wasp.resources.platform.inventory import PlatformInventory

    reader = MagicMock()
    guard = MagicMock()
    guard.check.return_value = (
        None,
        {"status": "unauthorized", "message": "Acesso negado."},
    )

    class FakeCtx:
        session_id = "tg:wasp-agent:999"

    result = PlatformInventory(guard=guard, reader=reader).get("acme", FakeCtx())

    assert result == {"status": "unauthorized", "message": "Acesso negado."}
    reader.get_by_name.assert_not_called()


def test_inventory_get_returns_error_on_exception():
    from wasp.resources.platform.inventory import PlatformInventory

    reader = MagicMock()
    reader.get_by_name.side_effect = RuntimeError("boom")
    guard = MagicMock()
    guard.check.return_value = ("local-operator", None)

    class FakeCtx:
        session_id = "local:wasp-agent:abc"

    result = PlatformInventory(guard=guard, reader=reader).get("acme", FakeCtx())

    assert result["status"] == "error"


def test_format_transition_date_returns_none_for_invalid_timestamp():
    from wasp.resources.platform.inventory import _format_transition_date

    assert _format_transition_date({"lastTransitionTime": "not-a-date"}) is None


def test_inventory_get_message_without_transition_time():
    from wasp.resources.platform.inventory import PlatformInventory

    reader = MagicMock()
    reader.get_by_name.return_value = {
        "metadata": {"name": "acme"},
        "status": {"conditions": [{"type": "Ready", "status": "False"}]},
    }
    guard = MagicMock()
    guard.check.return_value = ("local-operator", None)

    class FakeCtx:
        session_id = "local:wasp-agent:abc"

    result = PlatformInventory(guard=guard, reader=reader).get("acme", FakeCtx())

    assert result["status"] == "Pending"
    assert "acme" in result["message"]
