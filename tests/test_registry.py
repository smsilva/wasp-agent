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
