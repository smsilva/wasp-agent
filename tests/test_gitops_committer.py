from unittest.mock import MagicMock

import pytest


def test_commit_success():
    from wasp.gitops_committer import GitOpsCommitter

    client = MagicMock()
    committer = GitOpsCommitter(client=client)

    result = committer.commit(
        file_path="infrastructure/tenants/acme.yaml",
        yaml_content="apiVersion: x\n",
        commit_message="feat(tenants): provision acme",
    )

    assert result is None
    client.create_file.assert_called_once_with(
        path="infrastructure/tenants/acme.yaml",
        message="feat(tenants): provision acme",
        content="apiVersion: x\n",
        branch="dev",
    )


def test_commit_returns_already_provisioning_on_conflict():
    from wasp.git_client import FileAlreadyExistsError
    from wasp.gitops_committer import GitOpsCommitter

    client = MagicMock()
    client.create_file.side_effect = FileAlreadyExistsError(
        "infrastructure/tenants/acme.yaml"
    )
    committer = GitOpsCommitter(client=client)

    result = committer.commit(
        file_path="infrastructure/tenants/acme.yaml",
        yaml_content="x",
        commit_message="x",
    )

    assert result == {
        "status": "already_provisioning",
        "message": "Tenant 'acme' is already being provisioned.",
    }


def test_from_env_raises_when_pat_missing(monkeypatch):
    from wasp.gitops_committer import GitOpsCommitter

    monkeypatch.delenv("GH_PAT", raising=False)

    with pytest.raises(ValueError, match="GH_PAT not set"):
        GitOpsCommitter.from_env()


def test_from_env_uses_defaults(monkeypatch):
    from wasp.gitops_committer import GitOpsCommitter

    mock_client_cls = MagicMock()
    monkeypatch.setenv("GH_PAT", "fake-pat")
    monkeypatch.delenv("GITOPS_REPO", raising=False)
    monkeypatch.delenv("GITHUB_BASE_URL", raising=False)
    monkeypatch.setattr("wasp.gitops_committer.PyGithubClient", mock_client_cls)

    GitOpsCommitter.from_env()

    mock_client_cls.assert_called_once_with(
        pat="fake-pat",
        repo="smsilva/wasp-gitops",
        base_url="https://api.github.com",
    )


def test_from_env_uses_env_vars(monkeypatch):
    from wasp.gitops_committer import GitOpsCommitter

    mock_client_cls = MagicMock()
    monkeypatch.setenv("GH_PAT", "p")
    monkeypatch.setenv("GITOPS_REPO", "myorg/my-gitops")
    monkeypatch.setenv("GITHUB_BASE_URL", "http://localhost:3000/api/v3")
    monkeypatch.setattr("wasp.gitops_committer.PyGithubClient", mock_client_cls)

    GitOpsCommitter.from_env()

    mock_client_cls.assert_called_once_with(
        pat="p", repo="myorg/my-gitops", base_url="http://localhost:3000/api/v3"
    )
