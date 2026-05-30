# Production Readiness Checklist

Checklist vivo para dois usos:

1. **Scaffolding de projeto novo** — agente percorre as seções 1–2 integralmente e identifica as demais conforme o tipo de projeto.
2. **Production Readiness Review (PRR)** — antes de cada deploy/merge significativo, percorrer o checklist e filtrar a parte relevante ao escopo da mudança.

Derivado do corpo de conhecimento acumulado no `wasp-agent` e incorpora [Kubernetes Production Best Practices](https://learnkube.com/production-best-practices). Cada item indica a área, o que verificar/decidir/implementar, e uma referência ao spec de origem quando aplicável.

## Classificação de itens

Vocabulário importado do `docs/sdlc/02-design/2026-05-30-good-citizen-test.md` (spec da automação dessa verificação):

- **gate** — bloqueia o deploy/merge se falhar, salvo exceção registrada e dentro do TTL.
- **score** — soma para nível de maturidade; não bloqueia, mas atrasa promoção a tiers superiores.
- Níveis: **Bronze** (gates ok), **Prata** (gates + resiliência/observabilidade), **Ouro** (apto a workloads tier-1).

Quando um item não puder ser cumprido, registrar exceção com TTL em `exceptions.yaml` no GitOps em vez de marcar `N/A` silenciosamente.

---

## 1. Estrutura e documentação

- [ ] `CLAUDE.md` na raiz com princípios, convenções de código, comandos de validação e estrutura de pastas.
- [ ] `HANDOFF.md` na raiz para continuidade entre sessões de agente.
- [ ] `docs/sdlc/` com subpastas `01-exploration/`, `02-design/`, `03-execution/` e `archived/` em cada.
- [ ] `docs/architecture/` para decisões arquiteturais vivas (nunca arquivar — atualizar no lugar).
- [ ] `docs/runbooks/` para procedimentos manuais (setup, troubleshooting, smoke tests).
- [ ] `docs/security/issues/` para findings de segurança com formato padronizado (`SEC-NNN-<slug>.md`).
- [ ] Fluxo de docs definido: spec em `02-design/` antes de plano em `03-execution/` antes de código.

---

## 2. Fundações de código

- [ ] Linguagem e toolchain decididos (ex: Python + `uv` + `ruff`).
- [ ] Formatador e linter configurados e obrigatórios no pre-commit ou CI (`ruff check`, `ruff format`).
- [ ] 100% de cobertura de testes como requisito (ou % definida explicitamente).
- [ ] `Makefile` com targets canônicos: `format`, `test`, `e2e`, `lint`.
- [ ] Targets complexos extraídos para `scripts/<name>` em vez de inline no Makefile.
- [ ] `pyproject.toml` (ou equivalente) com dependências pinadas em lockfile.

---

## 3. Testes

### Unitários / integração
- [ ] Framework de teste configurado (`pytest` ou equivalente).
- [ ] Fixtures de mock para dependências externas (LLM, APIs de terceiros, banco).
- [ ] Cobertura medida e reportada (`pytest --cov`, `coverage.xml` para SonarQube).
- [ ] Módulos novos adicionados à lista de teardown de fixtures para evitar leak de estado.

### E2E
- [ ] Pipeline e2e automatizado que exercita o fluxo completo sem mocks de infra.
- [ ] `make e2e` documentado em `docs/runbooks/validation.md`.
- [ ] Separação clara entre o que `make test` verifica e o que só `make e2e` pega.

### Carga
- [ ] Baseline de latência medida antes de qualquer otimização (`wrk` ou `k6` no endpoint de health).
- [ ] Cenários de carga definidos: baseline, sustentado, spike, soak.
- [ ] Thresholds explícitos: p95 < Xms, taxa de erro < Y%.
- [ ] Estratégia para testar sem custo LLM real (mock ou modelo barato).
- [ ] Ref: `2026-05-26-load-testing.md`

---

## 4. Segurança

### Autenticação e autorização
- [ ] Mecanismo de auth definido antes de qualquer endpoint público.
- [ ] Allowlist de usuários com convite controlado (não auto-registro aberto).
- [ ] Operações check-then-write em banco usam transação com lock imediato (não SELECT + INSERT separados).
- [ ] Ref: `docs/runbooks/auth-admin.md`

### Análise estática (SAST / SCA)
- [ ] SonarQube ou SonarCloud configurado; Quality Gate definido antes de ligar no CI.
- [ ] Snyk Open Source para CVEs em dependências — fix suggestions automáticos.
- [ ] Snyk IaC para manifests Kubernetes/Helm antes do commit.
- [ ] `gitleaks` ou `trufflehog` no pre-commit para detectar segredos acidentais.
- [ ] Ref: `2026-05-26-code-quality-security-scanning.md`

### SBOM e supply chain
- [ ] `syft` configurado para gerar SBOM (`sbom.cdx.json`) do projeto.
- [ ] `grype` para escanear SBOM por CVEs — integrado ao CI ou `make scan-vulns`.
- [ ] VEX criado para falsos positivos confirmados (CVEs não exploráveis no contexto).
- [ ] SLSA 1 mínimo: provenance document gerado no CI para cada release.
- [ ] COSIGN para assinar imagem e SBOM quando houver distribuição formal.
- [ ] Ref: `2026-05-26-sbom.md`, `2026-05-26-supply-chain-security.md`

### Pentest
- [ ] Superfície de ataque mapeada: endpoints, canais de entrada, LLM, infra.
- [ ] Prompt injection testada (direct, indirect via tool results).
- [ ] Verificar que `/docs` (Swagger) e stack traces estão desabilitados em produção.
- [ ] `debug=False` em FastAPI (ou equivalente) antes de qualquer deploy externo.
- [ ] Ref: `2026-05-26-penetration-test.md`

### Kubernetes security
- [ ] ServiceAccount dedicada por workload; `automountServiceAccountToken: false` por padrão.
- [ ] Pod Security Standards: namespace anotado com `restricted` ou `baseline` via Pod Security Admission.
- [ ] Workload Identity (IRSA, GCP WI, Azure Entra) em vez de credenciais fixas em Secret.
- [ ] Admission controller (Kyverno ou ValidatingAdmissionPolicy) para enforcement de políticas de deployment.
- [ ] Ref: [learnkube.com/production-best-practices](https://learnkube.com/production-best-practices)

---

## 5. Observabilidade

- [ ] Endpoint de health (`/health` ou `/telemetry/health`) desde o primeiro deploy.
- [ ] Métricas Prometheus expostas (`/telemetry/prometheus` ou equivalente).
- [ ] Métricas LLM-específicas instrumentadas: tokens por turno, tokens por sessão, % do context window.
- [ ] Budget de tokens definido com alerta em threshold (context window saturation).
- [ ] Logs estruturados com `chat_id` pseudonimizado (nunca PII em claro) em todos os contextos.
- [ ] `ContextVar` (ou equivalente) propagado explicitamente para threads — não assume herança.
- [ ] Distributed tracing configurado (OpenTelemetry): spans para HTTP, auth, LLM, tools, GitOps.
- [ ] `trace_id` e `span_id` injetados nos logs estruturados para correlação.
- [ ] Alerting rules definidas em Prometheus/Alertmanager — métricas sem alertas não são monitoramento.
- [ ] Ref: `2026-05-20-token-cost-budget.md`, `2026-05-26-opentelemetry-tracing.md`

---

## 6. Entrega e distribuição

### Containerização
- [ ] `Dockerfile` com imagem mínima (distroless ou alpine), usuário não-root, `readOnlyRootFilesystem`.
- [ ] `.dockerignore` excluindo `.env`, `__pycache__`, arquivos de teste.
- [ ] Imagem versionada por tag imutável (`appVersion`) — nunca `latest` em produção.
- [ ] Container stateless: nenhum dado permanente em disco local — usar PersistentVolume ou store externo.
- [ ] Reconexão explícita implementada para conexões longas (gRPC, WebSocket, HTTP/2).

### Helm chart (se Kubernetes)
- [ ] `Chart.yaml` com `appVersion` sincronizado com a versão da imagem.
- [ ] `values.yaml` com todos os parâmetros documentados e defaults seguros.
- [ ] `values.schema.json` validando campos obrigatórios (webhook URL, existingSecret).
- [ ] Segredos via `existingSecret` — nunca valores em `values.yaml`.
- [ ] `securityContext` no Deployment: `runAsNonRoot`, `readOnlyRootFilesystem`, `allowPrivilegeEscalation: false`.
- [ ] `ServiceMonitor` opcional para Prometheus Operator.
- [ ] `NOTES.txt` com requisitos pós-install (TLS para webhook, namespace, etc.).
- [ ] Graceful shutdown: handler de SIGTERM + `terminationGracePeriodSeconds` alinhado ao draining.
- [ ] Startup, readiness e liveness probes definidas com timing explícito (não usar defaults do Kubernetes).
- [ ] `resources.requests` (CPU + memória) em todo container — base em dados de uso real.
- [ ] `resources.limits` de memória definido; usar `ephemeral-storage` em containers com escrita local.
- [ ] Rolling update: `maxUnavailable`, `maxSurge` e `minReadySeconds` explícitos no Deployment.
- [ ] `PodDisruptionBudget` com `minAvailable` para workloads que não toleram zero réplicas.
- [ ] `topologySpreadConstraints` quando há mais de uma réplica (distribuição multi-nó/zona).
- [ ] Labels `app.kubernetes.io/*` (`name`, `version`, `component`, `part-of`) em todos os recursos.
- [ ] Segredos montados como volume — nunca via `env[].valueFrom.secretKeyRef`.
- [ ] Ref: `2026-05-26-helm-chart.md`, [learnkube.com/production-best-practices](https://learnkube.com/production-best-practices)

### CI/CD
- [ ] Pipeline com: lint → test → build → scan (SBOM + CVE) → sign (COSIGN) → push.
- [ ] Quality Gate do SonarQube bloqueia merge se não atingido.
- [ ] SLSA provenance gerado como artefato de cada release.
- [ ] Semantic versioning adotado; `CHANGELOG.md` gerado automaticamente ou mantido manualmente.
- [ ] Dependabot ou Renovate configurado para PRs automáticos de atualização de dependências.
- [ ] Multi-environment (dev/staging/prod) definido: configs e segredos diferem por ambiente.

### Escalabilidade (Kubernetes)
- [ ] HPA configurado: `minReplicas`, `maxReplicas` e `stabilizationWindowSeconds` para scale-down conservador.
- [ ] KEDA se escala por fila ou lag (Kafka, SQS, RabbitMQ, etc.).
- [ ] `PriorityClass` definida por tier de criticidade — controla ordem de evicção sob pressão de recursos.
- [ ] Cost review após 1–2 semanas de produção: comparar `resources.requests` com uso real e ajustar.
- [ ] Ref: [learnkube.com/production-best-practices](https://learnkube.com/production-best-practices)

---

## 7. Rate Limiting e Resiliência

- [ ] Rate limiting por usuário/sessão definido antes de qualquer endpoint público.
- [ ] Comportamento sob rate limit: mensagem amigável, sem revelar limites, sem logar como erro.
- [ ] Model fallback strategy: se LLM primário indisponível, o agente falha graciosamente ou usa fallback?
- [ ] Secrets com expiração monitorados: alerta proativo antes de `GH_PAT` / tokens expirarem.
- [ ] Procedimento de rotação de segredos documentado em runbook.
- [ ] Ref: `2026-05-26-rate-limiting.md`, `2026-05-26-secret-rotation.md`

---

## 8. Métricas de engenharia (DORA)

- [ ] "Deploy" definido explicitamente (merge em main? tag? push para registry?).
- [ ] Timestamps de commit e deploy capturados para calcular Lead Time.
- [ ] Processo de registrar incidentes definido (para CFR e MTTR).
- [ ] Ref: `2026-05-26-dora-metrics.md`

---

## 9. Operações e Recovery

- [ ] RTO e RPO definidos explicitamente — mesmo que sejam "1 hora" e "24 horas".
- [ ] Inventário de estado persistente: o que existe, onde fica, o que é irrecuperável sem backup.
- [ ] Backup automatizado do estado crítico com destino separado do volume primário.
- [ ] Procedimento de restore testado ao menos uma vez antes de precisar.
- [ ] Incident response: classificação de severidade (SEV-1 a SEV-4) e SLO de resposta por nível.
- [ ] Post-mortem blameless após cada SEV-1/SEV-2.
- [ ] NetworkPolicy Kubernetes definida: restringir tráfego entre pods ao mínimo necessário.
- [ ] Ref: `2026-05-26-disaster-recovery.md`, `2026-05-26-incident-response.md`

---

## 10. Conformidade (se produto com usuários)

- [ ] Enquadramento EU AI Act verificado: proibido / alto risco / risco limitado / mínimo.
- [ ] Se chatbot (risco limitado): disclaimer "este é um agente IA" no onboarding e system prompt (Art. 50.1).
- [ ] Se alto risco: gestão de risco, logs automáticos, human oversight, documentação técnica.
- [ ] CRA (Cyber Resilience Act): SBOM como evidência de due diligence se produto distribuído na UE.
- [ ] Inventário de dados pessoais coletados: o que, onde, por quanto tempo, com quem é compartilhado.
- [ ] Política de retenção definida e mecanismo de apagamento implementado (GDPR Art. 17).
- [ ] `chat_id` e conteúdo de mensagens pseudonimizados em logs — nunca PII em claro.
- [ ] Transparência para usuários: informar sobre processamento por LLM externo (Anthropic).
- [ ] Ref: `2026-05-26-eu-ai-act.md`, `2026-05-26-privacy-data-retention.md`

---

## 11. LLM-specific (se aplicável)

- [ ] System prompt extraído para arquivo versionado — não embutido como string no código.
- [ ] Versão do prompt logada em cada chamada LLM para correlação com comportamento em produção.
- [ ] Golden set de cenários vinculado ao arquivo de prompt — CI roda evals ao detectar mudança.
- [ ] Rollback de prompt documentado: como reverter sem novo deploy de código.
- [ ] Model fallback: comportamento definido se API do LLM estiver fora ou rate-limited.
- [ ] Conteúdo de mensagens não incluído como atributo de span/métrica — apenas metadados.
- [ ] Ref: `2026-05-26-prompt-versioning.md`, `2026-05-20-llm-behavior-evaluation.md`

---

## 12. Canais de entrada (multi-channel)

Para projetos com mais de um canal de entrada (Telegram, Discord, Slack, webhook genérico), validar **cada canal individualmente** antes do deploy — gates em cluster não cobrem isso.

- [ ] Webhook/bot registrado no endpoint correto do ambiente alvo (gate).
- [ ] Token/segredo do canal válido e dentro do prazo de expiração (gate).
- [ ] Mensagem de teste fim-a-fim: input → auth → agent → notifier → resposta (gate).
- [ ] Fallback `local` (ou equivalente sem dependência externa) testado para diagnóstico (score).
- [ ] Comportamento sob token revogado/inválido: erro logado sem crash do processo (score).

---

## 13. Runbooks mínimos

- [ ] `docs/runbooks/validation.md` — índice de todos os caminhos de validação.
- [ ] Setup local (dependências, variáveis de ambiente, primeiro run).
- [ ] Como adicionar/revogar usuários autorizados.
- [ ] Como fazer rollback de um deploy problemático.
- [ ] Como interpretar um alerta de métricas.

---

## Uso por agente

**Scaffolding de projeto novo:**

1. Percorrer seções 1–2 integralmente — são pré-requisitos para tudo mais.
2. Identificar quais seções são relevantes para o tipo de projeto (LLM? API pública? Kubernetes? multi-channel?).
3. Criar um spec em `docs/sdlc/02-design/` para cada item marcado como "a decidir" antes de implementar.
4. Marcar itens como `N/A` com justificativa quando explicitamente fora de escopo — não silenciosamente ignorar.
5. Rever o checklist ao final de cada milestone para itens novos que se tornaram relevantes.

**Production Readiness Review (pedido tipo "está pronto pra prod?", "checklist de readiness"):**

1. Identificar o escopo da mudança (deploy de feature nova? release pontual? migração de infra?).
2. Filtrar as seções relevantes — não despejar o documento inteiro.
3. Reportar gates obrigatórios separados dos itens de score (mostrar o nível alvo vs. atingido).
4. Para itens não cumpridos, sugerir registrar exceção com TTL em `exceptions.yaml` em vez de simplesmente listar como pendente.
5. Se houver `2026-05-30-good-citizen-test.md` implementado, preferir executar `waspctl good-citizen run` em vez de checklist manual.