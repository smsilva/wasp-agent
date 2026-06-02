def test_cluster_provider_name(mock_agno):
    from wasp.resources.cluster.provider import ClusterProvider

    assert ClusterProvider().name == "cluster"


def test_cluster_provider_tools(mock_agno):
    from wasp.provision import (
        get_cluster_status,
        list_cluster_instances,
        provision_cluster_instance,
    )
    from wasp.resources.cluster.provider import ClusterProvider

    tools = ClusterProvider().tools()

    assert tools == [
        provision_cluster_instance,
        list_cluster_instances,
        get_cluster_status,
    ]


def test_cluster_provider_satisfies_protocol(mock_agno):
    from wasp.resources.cluster.provider import ClusterProvider
    from wasp.resources.protocol import ResourceProvider

    assert isinstance(ClusterProvider(), ResourceProvider)
