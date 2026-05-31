def test_platform_provider_name(mock_agno):
    from wasp.resources.platform.provider import PlatformProvider

    assert PlatformProvider().name == "platform"


def test_platform_provider_tools(mock_agno):
    from wasp.provision import (
        list_platform_instances,
        provision_platform_instance,
    )
    from wasp.resources.platform.provider import PlatformProvider

    tools = PlatformProvider().tools()

    assert tools == [provision_platform_instance, list_platform_instances]


def test_platform_provider_satisfies_protocol(mock_agno):
    from wasp.resources.platform.provider import PlatformProvider
    from wasp.resources.protocol import ResourceProvider

    assert isinstance(PlatformProvider(), ResourceProvider)
