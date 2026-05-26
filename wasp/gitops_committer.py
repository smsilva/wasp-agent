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
        return cls(
            PyGithubClient(
                pat=pat,
                repo=os.getenv("GITOPS_REPO", "smsilva/wasp-gitops"),
                base_url=os.getenv("GITHUB_BASE_URL", "https://api.github.com"),
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
