import base64
from typing import Protocol

import httpx
from github import Github
from github.GithubException import GithubException


class FileAlreadyExistsError(Exception):
    """Raised when create_file targets a path that already exists on the branch."""


class GitClient(Protocol):
    def create_file(self, path: str, message: str, content: str, branch: str) -> None: ...


class PyGithubClient:
    def __init__(self, pat: str, repo: str, base_url: str = "https://api.github.com"):
        self._repo = Github(login_or_token=pat, base_url=base_url).get_repo(repo)

    def create_file(self, path: str, message: str, content: str, branch: str) -> None:
        try:
            self._repo.create_file(path=path, message=message, content=content, branch=branch)
        except GithubException as e:
            if e.status == 422 and "sha" in str(e.data.get("message", "")).lower():
                raise FileAlreadyExistsError(path) from e
            raise


class GiteaClient:
    def __init__(self, token: str, repo: str, base_url: str):
        self._token = token
        self._repo = repo
        self._base_url = base_url

    def create_file(self, path: str, message: str, content: str, branch: str) -> None:
        encoded = base64.b64encode(content.encode()).decode()
        r = httpx.post(
            f"{self._base_url}/api/v1/repos/{self._repo}/contents/{path}",
            headers={"Authorization": f"token {self._token}"},
            json={"message": message, "content": encoded, "branch": branch},
            timeout=10,
        )
        r.raise_for_status()
