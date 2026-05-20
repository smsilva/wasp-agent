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

PyGithub **não funciona** contra Gitea para criação de arquivos. Dois bugs:

1. **Assertion de porta** (`PyGithub/Requester.py:902`): PyGithub valida que toda URL retornada pela API tem a mesma porta do `base_url`. Gitea inclui a porta interna `3000` nas response URLs mesmo quando exposto em outra porta externa (ex.: `3456`), causando `AssertionError: 3000` antes de qualquer request sair.
2. **Método HTTP**: Gitea 1.22 (e 1.21) usa `POST /repos/.../contents/{path}` para **criar** arquivos e `PUT` para **atualizar**. PyGithub `create_file()` usa `PUT`, e Gitea responde `422 "SHA Required"` para arquivos novos. GitHub aceita `PUT` em ambos os casos.

Por isso o código de produção usa `tools.git_client.PyGithubClient` (GitHub), e o E2E injeta `tools.git_client.GiteaClient` (httpx POST direto). Ver `tools/git_client.py`.

O repo deve ser inicializado com `auto_init: true` e o `default_branch` correto (ex.: `"dev"`) para o primeiro push funcionar imediatamente.

## Getting file content after a push

```
GET /api/v1/repos/<owner>/<repo>/raw/<path>?ref=<sha>
```

Use the commit SHA returned by `GET /api/v1/repos/<owner>/<repo>/commits?limit=1`.
