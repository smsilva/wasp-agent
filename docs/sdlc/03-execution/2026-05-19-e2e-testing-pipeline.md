# E2E Testing Pipeline — Plano de Execução

**Date:** 2026-05-19  
**Status:** In Progress  
**Spec:** `docs/sdlc/02-design/2026-05-19-e2e-testing-pipeline.md`

## Passos

1. `Notifier` protocol — `tools/notifier.py` + refactor `watcher.py` + testes unitários atualizados → verify: `pytest --cov` 100%, ruff clean
2. Configurabilidade git — `GITHUB_BASE_URL` + `GITOPS_REPO` em `provision.py` + testes unitários atualizados → verify: `pytest --cov` 100%, ruff clean
3. ✅ Fixtures E2E — `tests/e2e/conftest.py` (`k3d_cluster`, `gitea_container`, `fake_reconciler`, `agent_client`) + `platform-crd.yaml` + `RecordingNotifier.wait_for_message()` + guard e2e em `mock_agno` → verify: pytest 53/53, 100% cobertura, ruff clean
4. ✅ Teste E2E — `tests/e2e/test_full_provisioning_flow.py` → verify: `pytest tests/e2e/ -m e2e --no-cov` passa em menos de 5 min (requer k3d + Gitea + AWS creds)
5. ✅ CI — `.github/workflows/e2e.yaml` → trigger em PRs para `dev`, OIDC para AWS, `pytest tests/e2e/ -m e2e --no-cov`