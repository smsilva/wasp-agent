import os
from pathlib import PurePosixPath

from github.GithubException import GithubException

from wasp.git_client import FileAlreadyExistsError, GitClient, PyGithubClient


class GitOpsCommitter:
    def __init__(self, client: GitClient):
        self._client = client

    @classmethod
    def probe(cls) -> None:
        if not os.getenv("GH_PAT"):
            return
        try:
            cls.from_env()
        except GithubException as e:
            raise RuntimeError(
                f"GitHub token is invalid (HTTP {e.status}): {e.data.get('message', e)}"
            ) from e

    @classmethod
    def from_env(cls) -> "GitOpsCommitter":
        pat = os.getenv("GH_PAT")
        if not pat:
            raise ValueError("GH_PAT not set")
        repo = os.getenv("GITOPS_REPO")
        if not repo:
            raise ValueError("GITOPS_REPO not set")
        base_url = os.getenv("GITHUB_BASE_URL")
        if not base_url:
            raise ValueError("GITHUB_BASE_URL not set")
        return cls(
            PyGithubClient(
                pat=pat,
                repo=repo,
                base_url=base_url,
            )
        )

    def commit(
        self, file_path: str, yaml_content: str, commit_message: str
    ) -> dict | None:
        try:
            self._client.create_file(
                path=file_path,
                message=commit_message,
                content=yaml_content,
                branch="dev",
            )
        except FileAlreadyExistsError:
            name = PurePosixPath(file_path).stem
            return {
                "status": "already_provisioning",
                "message": f"Tenant '{name}' is already being provisioned.",
            }
        return None
