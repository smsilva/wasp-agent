# Code Quality & Security Scanning — SonarQube e Snyk

**Date:** 2026-05-26  
**Status:** Idea  

## Contexto

SonarQube e Snyk são ferramentas complementares de análise estática e scanning de segurança. Complementam o pipeline de supply chain security (`2026-05-26-supply-chain-security.md`) — enquanto aquele foca em integridade de artefatos e dependências, este foca em **qualidade do código-fonte** e **vulnerabilidades em dependências em tempo de desenvolvimento**.

## SonarQube

### O que é

Plataforma de **análise estática contínua** (SAST — Static Application Security Testing) que inspeciona código-fonte para detectar:

- Bugs (lógica incorreta, null dereferences, resource leaks)
- Code smells (complexidade ciclomática alta, duplicação, dead code)
- Security hotspots (padrões de código que podem ser vulnerabilidades)
- Vulnerabilidades de segurança mapeadas em CWE/OWASP Top 10
- Cobertura de testes e dívida técnica acumulada

### Conceitos-chave

**Quality Gate:** conjunto de condições que o código deve passar para ser considerado "pronto" (ex: cobertura ≥ 80%, zero vulnerabilidades críticas novas). Bloqueia merge se não atingido.

**Quality Profile:** conjunto de regras ativas por linguagem. Personalizável por projeto.

**Branches & PRs:** analisa código novo em PRs isoladamente ("new code") — evita que dívida legada bloqueie entregas novas.

**Security Hotspots vs Vulnerabilities:**
- *Hotspot*: padrão que requer revisão humana (pode ou não ser vulnerabilidade).
- *Vulnerability*: confirmado como problema de segurança.

### Modos de uso

| Modo | Quando usar |
|---|---|
| SonarQube Community (self-hosted) | Projeto pessoal/interno, zero custo |
| SonarCloud (SaaS) | Integração direta com GitHub/GitLab, grátis para projetos públicos |
| sonar-scanner CLI | CI local ou pipeline sem plugin nativo |

### Integração Python

```bash
sonar-scanner \
  --define sonar.projectKey=wasp-agent \
  --define sonar.sources=wasp \
  --define sonar.tests=tests \
  --define sonar.python.coverage.reportPaths=coverage.xml \
  --define sonar.python.version=3.12
```

`pytest --cov=wasp --cov-report=xml` gera o `coverage.xml` que o Sonar consome.

### Aplicação no wasp-agent

- `make sonar` rodando `sonar-scanner` localmente ou via SonarCloud.
- Quality Gate mínimo: zero vulnerabilidades críticas/altas novas; cobertura ≥ 100% (já exigida pelo projeto).
- Útil para detectar security hotspots em `wasp/auth.py` (SQLite, check-then-write) e `wasp/clients/telegram/webhook.py` (FastAPI, injeção de parâmetros).

---

## Snyk

### O que é

Plataforma de **segurança para desenvolvedores** com foco em quatro domínios:

| Domínio | O que faz |
|---|---|
| **Snyk Open Source** | Scan de dependências por CVEs (SCA — Software Composition Analysis) |
| **Snyk Code** | SAST — análise de código-fonte (similar ao SonarQube) |
| **Snyk Container** | Scan de imagens de container por vulnerabilidades |
| **Snyk IaC** | Scan de infraestrutura como código (Terraform, Helm, Kubernetes YAML) |

### Diferencial vs SonarQube

- **Foco em dependências:** Snyk Open Source é mais profundo que o SonarQube em SCA — rastreia árvore de dependências transitivas, sugere versão de fix, cria PRs automáticos.
- **Snyk IaC:** único dos dois que analisa manifests Kubernetes/Helm — relevante para o GitOps do wasp-agent.
- **Developer-first UX:** integração com IDE (VS Code plugin), feedback inline no editor.
- **Snyk Code** é o equivalente ao Sonar para SAST, mas com menor profundidade de regras para Python.

### Snyk vs grype/trivy (do SBOM doc)

| Ferramenta | Modelo | Atualização de DB | Fix suggestions |
|---|---|---|---|
| grype | Open source, offline-first | Pull manual | Não |
| trivy | Open source, offline-first | Pull manual | Não |
| Snyk Open Source | SaaS + CLI | Contínua (Snyk Intel) | Sim — PR automático |

Snyk tem base de vulnerabilidades própria (Snyk Intel) com curadoria manual, frequentemente mais atualizada que NVD.

### Snyk IaC no contexto do wasp-agent

O agente gera e commita manifests Kubernetes (Crossplane Composition, ArgoCD Application). `snyk iac test` pode escanear esses arquivos antes do commit:

```bash
snyk iac test wasp/resources/
```

Detecta: containers sem `securityContext`, permissões excessivas, `hostNetwork: true`, segredos em plaintext, etc.

### Licenciamento

- **Grátis:** projetos open source, limite de 200 testes/mês no plano free.
- **Team/Enterprise:** ilimitado, PRs automáticos, relatórios.
- CLI open source; análise feita na nuvem Snyk.

---

## SonarQube vs Snyk — quando usar cada um

| Necessidade | Ferramenta |
|---|---|
| Qualidade de código, complexidade, code smells | SonarQube |
| SAST profundo em Python | SonarQube |
| CVEs em dependências PyPI com fix suggestions | Snyk Open Source |
| Scan de manifests Kubernetes/Helm | Snyk IaC |
| Scan de imagens de container | Snyk Container ou trivy |
| Pipeline offline (air-gapped) | grype/trivy (não Snyk) |
| Projeto open source, custo zero | SonarCloud (grátis) + Snyk free tier |

Recomendação para wasp-agent: **SonarCloud** (grátis, integração GitHub nativa) + **Snyk free tier** (CVEs + IaC scan). São complementares, não concorrentes.

---

## Conexão com outros specs

- **SBOM (`2026-05-26-sbom.md`):** Snyk Open Source complementa `grype` — cobre o mesmo domínio (CVEs em dependências) com base de dados diferente e fix suggestions.
- **Supply Chain (`2026-05-26-supply-chain-security.md`):** SonarQube/Snyk atuam em tempo de desenvolvimento; SLSA/COSIGN atuam em tempo de build/distribuição. Camadas distintas.
- **EU AI Act (`2026-05-26-eu-ai-act.md`):** CRA exige "due diligence" em segurança de software — SonarQube Quality Gate e Snyk scan são evidências auditáveis.
- **DORA Metrics (`2026-05-26-dora-metrics.md`):** CFR reduz quando vulnerabilidades são detectadas antes do deploy. Quality Gate integrado ao PR é o mecanismo.

## Armadilhas

- **Ruído sem triage.** SonarQube e Snyk geram muitos findings no início. Definir Quality Gate antes de ligar — não bloquear o pipeline com centenas de issues legados de uma vez.
- **Sobreposição não gerenciada.** SBOM + grype + Snyk Open Source fazem SCA. Escolher um como fonte de verdade para CVEs de dependências; usar os outros como camada de verificação.
- **Snyk IaC sem contexto de runtime.** Detecta configurações permissivas, mas não sabe o que é intencional no seu cluster. Tunar supressões antes de integrar ao CI.
- **SonarQube sem cobertura XML.** Sem o relatório de cobertura, o Sonar não sabe quais linhas foram exercitadas — métricas de cobertura ficam zeradas.

## Fora de escopo desta nota

- Integração com SIEM (Splunk, Elastic) para correlação de findings.
- Snyk Enterprise features (políticas corporativas, SSO).
- Comparação detalhada de regras SAST entre SonarQube e Snyk Code.

## Próximo passo

Promover a Draft quando CI for adicionado. Ação imediata de custo zero: rodar `snyk iac test wasp/resources/` localmente nos manifests Kubernetes existentes para ter baseline de findings.

## Referências

- [SonarQube docs](https://docs.sonarqube.org/)
- [SonarCloud](https://sonarcloud.io/) — SaaS grátis para projetos públicos
- [Snyk docs](https://docs.snyk.io/)
- [Snyk CLI](https://github.com/snyk/cli)
- [Snyk vs SonarQube — comparação oficial Snyk](https://snyk.io/vs/sonarqube/)