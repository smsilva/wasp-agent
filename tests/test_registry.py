def test_resource_provider_protocol_runtime_checkable(mock_agno):
    from collections.abc import Callable
    from wasp.resources.protocol import ResourceProvider

    class FakeProvider:
        name = "fake"

        def tools(self) -> list[Callable]:
            return []

    assert isinstance(FakeProvider(), ResourceProvider)


def test_resource_provider_rejects_non_conforming(mock_agno):
    from wasp.resources.protocol import ResourceProvider

    class NotAProvider:
        pass

    assert not isinstance(NotAProvider(), ResourceProvider)


def test_all_tools_aggregates_providers(mock_agno):
    from wasp.resources.registry import ResourceRegistry

    def tool_a():
        return "a"

    def tool_b():
        return "b"

    def tool_c():
        return "c"

    class ProviderOne:
        name = "one"

        def tools(self):
            return [tool_a, tool_b]

    class ProviderTwo:
        name = "two"

        def tools(self):
            return [tool_c]

    registry = ResourceRegistry([ProviderOne(), ProviderTwo()])

    assert registry.all_tools() == [tool_a, tool_b, tool_c]


def test_all_tools_empty_when_no_providers(mock_agno):
    from wasp.resources.registry import ResourceRegistry

    registry = ResourceRegistry([])

    assert registry.all_tools() == []


def test_discover_loads_providers_from_registry(mock_agno, monkeypatch):
    from wasp.resources import registry as registry_mod
    from wasp.resources.registry import ResourceRegistry

    def tool_x():
        return "x"

    class DiscoveredProvider:
        name = "discovered"

        def tools(self):
            return [tool_x]

    monkeypatch.setattr(registry_mod, "PROVIDERS", ["fake.module:DiscoveredProvider"])
    monkeypatch.setattr(registry_mod, "_load", lambda path: DiscoveredProvider)

    registry = ResourceRegistry.discover()

    assert registry.all_tools() == [tool_x]


def test_discover_empty_when_no_providers_registered(mock_agno, monkeypatch):
    from wasp.resources import registry as registry_mod
    from wasp.resources.registry import ResourceRegistry

    monkeypatch.setattr(registry_mod, "PROVIDERS", [])

    registry = ResourceRegistry.discover()

    assert registry.all_tools() == []


def test_load_resolves_dotted_path(mock_agno):
    from wasp.resources.platform.provider import PlatformProvider
    from wasp.resources.registry import _load

    assert (
        _load("wasp.resources.platform.provider:PlatformProvider") is PlatformProvider
    )
