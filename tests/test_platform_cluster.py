from unittest.mock import MagicMock


def test_list_with_status_empty():
    from wasp.platform_cluster import PlatformClusterReader

    api = MagicMock()
    api.list_cluster_custom_object.return_value = {"items": []}

    result = PlatformClusterReader(api=api).list_with_status()

    assert result == []


def test_list_with_status_ready():
    from wasp.platform_cluster import PlatformClusterReader

    api = MagicMock()
    api.list_cluster_custom_object.return_value = {
        "items": [
            {
                "metadata": {"name": "acme"},
                "status": {"conditions": [{"type": "Ready", "status": "True"}]},
            }
        ]
    }

    result = PlatformClusterReader(api=api).list_with_status()

    assert result == [{"name": "acme", "status": "Ready"}]


def test_list_with_status_pending():
    from wasp.platform_cluster import PlatformClusterReader

    api = MagicMock()
    api.list_cluster_custom_object.return_value = {
        "items": [
            {
                "metadata": {"name": "globex"},
                "status": {"conditions": [{"type": "Ready", "status": "False"}]},
            }
        ]
    }

    result = PlatformClusterReader(api=api).list_with_status()

    assert result == [{"name": "globex", "status": "Pending"}]


def test_list_with_status_unknown_when_no_ready_condition():
    from wasp.platform_cluster import PlatformClusterReader

    api = MagicMock()
    api.list_cluster_custom_object.return_value = {
        "items": [
            {"metadata": {"name": "fresh"}, "status": {"conditions": []}},
            {"metadata": {"name": "noinfo"}},
        ]
    }

    result = PlatformClusterReader(api=api).list_with_status()

    assert result == [
        {"name": "fresh", "status": "Unknown"},
        {"name": "noinfo", "status": "Unknown"},
    ]


def test_list_calls_api_with_correct_group_version_plural():
    from wasp.platform_cluster import PlatformClusterReader

    api = MagicMock()
    api.list_cluster_custom_object.return_value = {"items": []}

    PlatformClusterReader(api=api).list_with_status()

    api.list_cluster_custom_object.assert_called_once_with(
        group="wasp.silvios.me",
        version="v1alpha1",
        plural="platforms",
    )


def test_from_env_uses_kube_config(monkeypatch):
    from wasp.platform_cluster import PlatformClusterReader

    mock_api = MagicMock()
    monkeypatch.setattr("wasp.platform_cluster.load_kube_config_auto", lambda: mock_api)

    reader = PlatformClusterReader.from_env()

    assert reader._api is mock_api
