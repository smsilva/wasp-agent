import base64
from unittest.mock import MagicMock


def test_pygithub_client_init_calls_get_repo(monkeypatch):
    from wasp import git_client

    mock_github_cls = MagicMock()
    mock_repo = MagicMock()
    mock_github_cls.return_value.get_repo.return_value = mock_repo

    monkeypatch.setattr(git_client, "Github", mock_github_cls)

    client = git_client.PyGithubClient(
        pat="tok", repo="owner/repo", base_url="https://api.github.com"
    )

    mock_github_cls.assert_called_once_with(
        login_or_token="tok", base_url="https://api.github.com"
    )
    mock_github_cls.return_value.get_repo.assert_called_once_with("owner/repo")
    assert client._repo is mock_repo


def test_pygithub_client_create_file_delegates(monkeypatch):
    from wasp import git_client

    mock_github_cls = MagicMock()
    mock_repo = MagicMock()
    mock_github_cls.return_value.get_repo.return_value = mock_repo
    monkeypatch.setattr(git_client, "Github", mock_github_cls)

    client = git_client.PyGithubClient(pat="t", repo="o/r")
    client.create_file(path="a.yaml", message="msg", content="body", branch="dev")

    mock_repo.create_file.assert_called_once_with(
        path="a.yaml", message="msg", content="body", branch="dev"
    )


def test_gitea_client_create_file_posts_base64(monkeypatch):
    from wasp import git_client

    captured = {}

    def fake_post(url, headers, json, timeout):
        captured["url"] = url
        captured["headers"] = headers
        captured["json"] = json
        captured["timeout"] = timeout
        r = MagicMock()
        r.raise_for_status.return_value = None
        return r

    monkeypatch.setattr(git_client.httpx, "post", fake_post)

    client = git_client.GiteaClient(
        token="tok", repo="root/wasp-gitops", base_url="http://localhost:3456"
    )
    client.create_file(path="infra/x.yaml", message="commit", content="hello", branch="dev")

    assert captured["url"] == (
        "http://localhost:3456/api/v1/repos/root/wasp-gitops/contents/infra/x.yaml"
    )
    assert captured["headers"] == {"Authorization": "token tok"}
    assert captured["json"]["message"] == "commit"
    assert captured["json"]["branch"] == "dev"
    assert base64.b64decode(captured["json"]["content"]).decode() == "hello"
    assert captured["timeout"] == 10


def test_gitea_client_raises_on_http_error(monkeypatch):
    import httpx as real_httpx

    from wasp import git_client

    def fake_post(*_args, **_kwargs):
        r = MagicMock()
        r.raise_for_status.side_effect = real_httpx.HTTPStatusError(
            "boom", request=MagicMock(), response=MagicMock()
        )
        return r

    monkeypatch.setattr(git_client.httpx, "post", fake_post)

    client = git_client.GiteaClient(token="t", repo="o/r", base_url="http://x")

    try:
        client.create_file(path="p", message="m", content="c", branch="dev")
    except real_httpx.HTTPStatusError:
        pass
    else:
        raise AssertionError("expected HTTPStatusError")
