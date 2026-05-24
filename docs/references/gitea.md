# Gitea

Used in E2E tests as a local Git server that PyGithub can talk to via `base_url`.

## Docker setup

- Image: `gitea/gitea:1.22`. Pin the minor version — the API changes between releases.
- Required env vars: `GITEA__security__INSTALL_LOCK=true` (skips the installation wizard), `GITEA__server__OFFLINE_MODE=true`.
- Gitea refuses to run as root. `docker exec` defaults to root — always pass `--user git`: `docker exec --user git <container> gitea admin user create ...`.

## Admin user creation

Run after the container is healthy (poll `GET /api/v1/version`):

```
docker exec --user git <container> gitea admin user create \
  --username root --password <pass> --email root@localhost \
  --admin --must-change-password=false
```

## API token scopes (v1.22+)

Token creation requires explicit scopes — `{"name": "..."}` alone returns 400:

```json
{"name": "e2e-token", "scopes": ["write:repository", "read:user"]}
```

Scope reference for this project:
- `write:repository` — push files (`repo.create_file`)
- `read:user` — read user info
- Creating repos via `POST /api/v1/user/repos` requires `write:user`

## PyGithub incompatibility

PyGithub **does not work** against Gitea for file creation. Two bugs:

1. **Port assertion** (`PyGithub/Requester.py:902`): PyGithub validates that every URL returned by the API uses the same port as `base_url`. Gitea includes the internal port `3000` in response URLs even when exposed on a different external port (e.g. `3456`), causing `AssertionError: 3000` before any request leaves.
2. **HTTP method**: Gitea 1.22 (and 1.21) uses `POST /repos/.../contents/{path}` to **create** files and `PUT` to **update**. PyGithub `create_file()` uses `PUT`, and Gitea responds `422 "SHA Required"` for new files. GitHub accepts `PUT` in both cases.

Production code uses `wasp.git_client.PyGithubClient` (GitHub); E2E tests inject `wasp.git_client.GiteaClient` (direct httpx POST). See `wasp/git_client.py`.

The repo must be initialized with `auto_init: true` and the correct `default_branch` (e.g. `"dev"`) for the first push to succeed immediately.

## Getting file content after a push

```
GET /api/v1/repos/<owner>/<repo>/raw/<path>?ref=<sha>
```

Use the commit SHA returned by `GET /api/v1/repos/<owner>/<repo>/commits?limit=1`.
