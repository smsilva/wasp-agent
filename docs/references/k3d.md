# k3d

Used in E2E tests to create ephemeral Kubernetes clusters locally and in CI.

- Create cluster and wait until ready: `k3d cluster create <name> --wait --timeout 90s`. Without `--wait` the cluster may not be ready for `kubectl apply`.
- Context name format: `k3d-<cluster-name>`. Always pass `--context k3d-<name>` to `kubectl` commands to avoid operating on the wrong cluster when multiple contexts exist.
- Load kubeconfig in Python: `k8s_config.load_kube_config(context="k3d-<name>")` — never call the parameterless form inside a test fixture (may pick up a production context).
- CRDs must be standard Kubernetes `apiextensions.k8s.io/v1` CRDs, not Crossplane XRDs (`apiextensions.crossplane.io/v2`). Crossplane is not installed — install only what the test needs.
- To patch status subresource, the CRD must declare `subresources: status: {}`. Without this, `patch_cluster_custom_object_status` returns 404.
- CI: `ubuntu-latest` ships with Docker but not k3d. Install via the official script: `curl -s https://raw.githubusercontent.com/k3d-io/k3d/main/install.sh | bash`.
- Teardown: `k3d cluster delete <name>`. k3d automatically removes the kubeconfig context on delete.
