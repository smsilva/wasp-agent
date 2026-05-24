# Pipeline E2E — automatizado

`make e2e`. Valida o fluxo agente → Git → cluster com Crossplane, GitHub e Telegram simulados localmente.

| Componente | Substituto |
|---|---|
| Cluster Kubernetes | k3d **barebones** (só o CRD `Platform` aplicado) |
| Crossplane | `fake_reconciler` em `tests/e2e/conftest.py` (patcheia `status.Ready=True`) |
| GitHub | Container Gitea local |
| Telegram | `RecordingNotifier` (in-memory) |
| HTTP | `httpx.ASGITransport(app=main.app)` |

```bash
make k3d-up    # cluster + Platform CRD
make e2e
make k3d-down
```

CI: `.github/workflows/e2e.yaml` (sobe k3d ephemeral, sem precisar de `make k3d-up` manual).

`make k3d-up` **não** instala ArgoCD nem Crossplane — é o cluster mínimo para os testes E2E.
