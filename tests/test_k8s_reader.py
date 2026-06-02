from unittest.mock import MagicMock


def test_search_for_instance_of_empty():
    from wasp.clients.k8s import KubernetesResourceReader

    api = MagicMock()
    api.list_cluster_custom_object.return_value = {"items": []}

    result = KubernetesResourceReader(api=api).search_for_instance_of(
        group="wasp.silvios.me", version="v1alpha1", plural="platforms"
    )

    assert result == []


def test_search_for_instance_of_returns_raw_items():
    from wasp.clients.k8s import KubernetesResourceReader

    api = MagicMock()
    api.list_cluster_custom_object.return_value = {
        "items": [
            {"metadata": {"name": "acme"}, "status": {"conditions": []}},
            {"metadata": {"name": "globex"}},
        ]
    }

    result = KubernetesResourceReader(api=api).search_for_instance_of(
        group="wasp.silvios.me", version="v1alpha1", plural="platforms"
    )

    assert result == [
        {"metadata": {"name": "acme"}, "status": {"conditions": []}},
        {"metadata": {"name": "globex"}},
    ]


def test_search_for_instance_of_calls_api_with_args():
    from wasp.clients.k8s import KubernetesResourceReader

    api = MagicMock()
    api.list_cluster_custom_object.return_value = {"items": []}

    KubernetesResourceReader(api=api).search_for_instance_of(
        group="example.com", version="v2", plural="widgets"
    )

    api.list_cluster_custom_object.assert_called_once_with(
        group="example.com", version="v2", plural="widgets"
    )


def test_from_env_uses_kube_config(monkeypatch):
    from wasp.clients.k8s import KubernetesResourceReader

    mock_api = MagicMock()
    monkeypatch.setattr(
        "wasp.clients.k8s.reader.load_kube_config_auto", lambda: mock_api
    )

    reader = KubernetesResourceReader.from_env()

    assert reader._api is mock_api


def test_load_kube_config_auto_incluster(monkeypatch):
    import wasp.clients.k8s as k8s

    monkeypatch.setattr(k8s.config, "load_incluster_config", lambda: None)
    monkeypatch.setattr(k8s.config, "load_kube_config", MagicMock())
    monkeypatch.setattr(k8s.client, "CustomObjectsApi", MagicMock())

    k8s.load_kube_config_auto()

    k8s.config.load_kube_config.assert_not_called()


def test_load_kube_config_auto_fallback_local(monkeypatch):
    import wasp.clients.k8s as k8s

    class FakeConfigException(Exception):
        pass

    # ConfigException must be a real Exception subclass for raise/except to work with mocked module
    monkeypatch.setattr(k8s.config, "ConfigException", FakeConfigException)

    def raise_(*a, **kw):
        raise FakeConfigException("not in cluster")

    incluster = MagicMock(side_effect=raise_)
    local = MagicMock()
    monkeypatch.setattr(k8s.config, "load_incluster_config", incluster)
    monkeypatch.setattr(k8s.config, "load_kube_config", local)
    monkeypatch.setattr(k8s.client, "CustomObjectsApi", MagicMock())

    k8s.load_kube_config_auto()

    incluster.assert_called_once()
    local.assert_called_once()


def test_get_by_name_returns_item():
    from wasp.clients.k8s import KubernetesResourceReader

    api = MagicMock()
    api.get_cluster_custom_object.return_value = {
        "metadata": {"name": "acme"},
        "status": {"conditions": []},
    }

    result = KubernetesResourceReader(api=api).get_by_name(
        group="wasp.silvios.me", version="v1alpha1", plural="platforms", name="acme"
    )

    assert result == {"metadata": {"name": "acme"}, "status": {"conditions": []}}
    api.get_cluster_custom_object.assert_called_once_with(
        group="wasp.silvios.me", version="v1alpha1", plural="platforms", name="acme"
    )


def test_get_by_name_reraises_non_404_exceptions():
    from wasp.clients.k8s import KubernetesResourceReader
    import pytest

    class FakeApiException(Exception):
        def __init__(self, status):
            self.status = status

    api = MagicMock()
    api.get_cluster_custom_object.side_effect = FakeApiException(status=500)

    with pytest.raises(FakeApiException):
        KubernetesResourceReader(api=api).get_by_name(
            group="wasp.silvios.me", version="v1alpha1", plural="platforms", name="acme"
        )


def test_get_by_name_returns_none_when_not_found():
    from wasp.clients.k8s import KubernetesResourceReader

    class FakeApiException(Exception):
        def __init__(self, status):
            self.status = status

    api = MagicMock()
    api.get_cluster_custom_object.side_effect = FakeApiException(status=404)

    result = KubernetesResourceReader(api=api).get_by_name(
        group="wasp.silvios.me", version="v1alpha1", plural="platforms", name="missing"
    )

    assert result is None
