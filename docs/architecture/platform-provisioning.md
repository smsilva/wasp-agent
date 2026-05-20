# Platform provisioning

- GitOps repo: `smsilva/wasp-gitops`, branch `dev`, path `infrastructure/tenants/{name}.yaml`.
- CRD: `apiVersion: wasp.silvios.me/v1alpha1`, `kind: Platform`. Uses standard Kubernetes `metadata.name`.
- Endpoint derived deterministically: `gateway.{aws-region}.{name}.{domain}` — no unknown fields at commit time.
- Services are fixed for all instances: auth, discovery, callback, portal.
- Default domain: `wasp.silvios.me`. Default region: `us-east-1`.
- Use Pydantic models to generate the manifest (not Jinja2). LLM extracts parameters; Pydantic validates and serializes. Never ask the LLM to generate Crossplane YAML directly.
- Provisioning tools use LLM confirmation (system prompt) — `@tool(requires_confirmation=True)` is incompatible with the Telegram interface (no handler for `RunPausedEvent`).
- Always use `yaml.safe_dump()` (not `yaml.dump()`) when serializing manifests — prevents LLM/user input from injecting arbitrary Python objects into the YAML.
- `list` parameters with defaults in tool functions: use a tuple constant (`DEFAULT_REGIONS = ("us-east-1",)`) and `None` in the signature, initializing in the body. Mutable list defaults are a Python gotcha.
- Sanitize user strings before interpolating into commit messages: `value.replace("\n", " ").replace("\r", " ")` — prevents extra line injection.
- Provisioning tool errors must return a generic dict `{"status": "error", "message": "..."}` — never `raise`, to avoid leaking internals to the user via LLM.
- The LLM surfaces **all fields** from a tool's returned dict. Include only fields with value to the end user; exclude `commit_sha`, `file_path`, internal system names (e.g., "ArgoCD").
- `GH_PAT`: fine-grained PAT on GitHub with minimum scope (`smsilva/wasp-gitops`, Contents: write). See `docs/runbooks/github-pat-setup.md`.
- Git push é abstraído por `wasp/git_client.py`: `GitClient` Protocol + `PyGithubClient` (produção, GitHub via PyGithub) + `GiteaClient` (E2E, httpx direto). `provision.py` instancia `PyGithubClient`; testes E2E injetam `GiteaClient` via monkeypatch. Padrão simétrico ao `Notifier` em `wasp/notifier.py`. Motivo: PyGithub é incompatível com Gitea (porta interna em response URLs + método PUT vs POST para criação de arquivo) — ver `docs/references/gitea.md`.

For the complete design, see `docs/sdlc/02-design/2026-05-15-platform-provisioning-design.md`.

To create a k3d cluster with ArgoCD, Crossplane, and the `wasp-gitops` Application syncing `infrastructure/tenants` from `smsilva/wasp-gitops` (branch `dev`), see `docs/runbooks/k3d-argocd-wasp-gitops.md`. The Application manifest is at `manifests/argocd/wasp-gitops-application.yaml`. The cluster creation script is at `~/git/kubernetes/lab/argo/argocd/run` (`smsilva/kubernetes` repo) — it orchestrates: k3d-cluster-creation → argocd-install → argocd-notification → crossplane-install → argocd-get-initial-password.

- Crossplane: version 2.2.1, namespace `crossplane-system`, script `crossplane-install.sh` in the same directory as `run`.
- `smsilva/kubernetes` uses `main` as the principal branch — always create a feature branch before committing.
- Local manifests are in `manifests/` at the project root — subdirs: `crossplane/xrd/`, `crossplane/compositions/`, `crossplane/functions/`, `crossplane/providers/`, `crossplane/providerconfigs/`, `argocd/`, `tenants/`.
- XRD uses `apiextensions.crossplane.io/v2` with `spec.scope: Cluster`. The `scope` field is immutable after creation — changing it requires deleting and recreating the XRD (destructive to existing CRs).
- Composition uses `apiextensions.crossplane.io/v1` (no v2). The `spec.resources` mode was REMOVED in Crossplane v2 — use `spec.mode: Pipeline` with `function-patch-and-transform`. Manifest in `manifests/crossplane/functions/`.
- When the Composition creates resources in a dedicated namespace, it must also create the `Namespace` — provider-kubernetes does not create it automatically. Add the Namespace `Object` before other resources in the pipeline.
- Pin the provider SA: create a `DeploymentRuntimeConfig` with `spec.serviceAccountTemplate.metadata.name: provider-kubernetes` and reference it in the `Provider` via `spec.runtimeConfigRef.name`. The Deployment name still tracks the revision, but `serviceAccountName` becomes pinned and the `ClusterRoleBinding` remains stable across reinstalls.