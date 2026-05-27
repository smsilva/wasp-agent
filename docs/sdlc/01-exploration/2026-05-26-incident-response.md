# Incident Response Playbook

**Date:** 2026-05-26  
**Status:** Idea  

## Contexto

O DORA spec (`2026-05-26-dora-metrics.md`) define MTTR como métrica de estabilidade, mas não descreve *como* responder a um incidente. Sem um playbook, MTTR alto não é só métrica ruim — é operação improvisada sob pressão: quais logs checar primeiro? quando escalar? como comunicar usuários? o que constitui "recuperado"?

Este spec não é um runbook operacional (esse fica em `docs/runbooks/`) — é a *decisão de design* sobre como incidentes serão classificados, respondidos e aprendidos.

## Classificação de severidade

| Severity | Critério | Exemplo | SLO de resposta |
|---|---|---|---|
| **SEV-1** | Serviço completamente indisponível ou dados corrompidos | Agent não responde a nenhuma mensagem; banco de auth corrompido | 15 min |
| **SEV-2** | Funcionalidade core degradada | Provisioning falha para todos os usuários; webhook recebendo mas não processando | 1 hora |
| **SEV-3** | Funcionalidade não-core afetada ou impacto parcial | Telemetria indisponível; rate limiting falso-positivo para um usuário | 4 horas |
| **SEV-4** | Comportamento inesperado sem impacto imediato | LLM respondendo com tom diferente; log de erro não crítico | Próximo sprint |

## Detecção

Caminhos de detecção esperados, em ordem de confiabilidade:

1. **Alertmanager / Prometheus** — alertas automáticos em threshold de métricas.
2. **Usuário reporta** — mensagem no canal de operação ou Telegram direto.
3. **Health check falha** — probe do Kubernetes reinicia o pod; notificação via ArgoCD.
4. **Log scan manual** — durante revisão de rotina.

Para cada caminho, o runbook de validação (`docs/runbooks/validation.md`) deve ter uma seção "o que checar primeiro".

## Primeiros 5 minutos (SEV-1 / SEV-2)

1. **Confirmar o escopo:** o serviço está completamente fora ou parcialmente degradado? Um usuário ou todos?
2. **Preservar evidências:** não reiniciar pods antes de capturar logs — `kubectl logs <pod> --previous` se já reiniciou.
3. **Isolar a causa provável:** última mudança deployada (git log), último alerta disparado, último evento no ArgoCD.
4. **Decidir: mitigar agora ou investigar?** Se o impacto é severo e há um rollback seguro disponível, fazer rollback primeiro, investigar depois.
5. **Comunicar** (ver seção abaixo).

## Mitigação vs. resolução

**Mitigação** = reduzir impacto imediatamente, mesmo sem entender a causa raiz.
- Rollback de deploy: `helm rollback wasp-agent`
- Reverter prompt: `git revert <commit>` + deploy
- Desabilitar funcionalidade: feature flag ou `WASP_AGENT_NOTIFIER=console` para desconectar Telegram

**Resolução** = corrigir a causa raiz.
- Identificar root cause via logs, traces, reprodução.
- Escrever fix com teste de regressão.
- Deploy e verificação.

MTTR do DORA mede até a **mitigação** (serviço restaurado), não até a resolução completa.

## Comunicação durante incidente

Para projeto pessoal com poucos usuários: mensagem direta no Telegram para usuários afetados.

Template:
```
[WASP] Identificamos uma instabilidade no agente desde HH:MM.
Impacto: [descrição breve].
Estimativa de resolução: [tempo ou "investigando"].
Atualizações a cada 30 minutos.
```

**Não revelar:** detalhes técnicos de infra, nomes de serviços internos, stack traces.

## Post-mortem

Após cada SEV-1 ou SEV-2 resolvido, criar `docs/security/issues/` (se security) ou `docs/sdlc/01-exploration/post-mortem-YYYY-MM-DD-<slug>.md` com:

| Campo | Conteúdo |
|---|---|
| **Timeline** | Detecção → primeiros 5 min → mitigação → resolução |
| **Root cause** | Uma frase descrevendo a causa raiz real |
| **Contributing factors** | O que permitiu que o problema acontecesse |
| **Impact** | Duração, usuários afetados, dados afetados |
| **What went well** | O que funcionou na resposta |
| **Action items** | Tasks concretas para prevenir recorrência |

Regra: post-mortem blameless — o objetivo é melhorar o sistema, não apontar culpados.

## Runbooks de incidentes comuns

A criar em `docs/runbooks/` quando os cenários forem conhecidos:

- `incident-pod-crashloop.md` — pod em CrashLoopBackOff: como identificar causa e restaurar.
- `incident-db-locked.md` — SQLite `database is locked`: diagnóstico e recovery.
- `incident-llm-unavailable.md` — API Anthropic fora ou rate-limited: fallback e comunicação.
- `incident-github-pat-expired.md` — PAT expirado: rotação de segredo sem downtime.
- `incident-telegram-webhook-broken.md` — Webhook Telegram não recebendo: diagnóstico de URL, TLS, ngrok.

## Métricas de incidente

Registrar em cada post-mortem para alimentar DORA:

- `time_to_detect` — quando o incidente começou vs. quando foi detectado.
- `time_to_mitigate` — quando o serviço foi restaurado (= MTTR do DORA).
- `time_to_resolve` — quando a causa raiz foi corrigida.
- `severity` — SEV-1 a SEV-4.
- `trigger` — deploy, config change, dependência externa, bug latente.

## Conexão com outros specs

- **DORA Metrics (`2026-05-26-dora-metrics.md`):** este spec implementa o processo que alimenta MTTR e CFR.
- **Secret Rotation (`2026-05-26-secret-rotation.md`):** expiração de segredo é incidente recorrente com playbook específico.
- **Disaster Recovery (`2026-05-26-disaster-recovery.md`):** loss de dados é SEV-1 com playbook de restore.
- **Rate Limiting (`2026-05-26-rate-limiting.md`):** flood de usuário é SEV-3/4 com resposta automatizada, não manual.
- **Observabilidade:** sem métricas e logs, os primeiros 5 minutos são às cegas.

## Armadilhas

- **Resolver sem post-mortem.** A pressão pós-incidente é para "seguir em frente". Post-mortem adiado vira post-mortem nunca feito.
- **Post-mortem que culpa pessoa.** Desmotiva reporte honesto de incidentes futuros.
- **Rollback como resposta padrão para tudo.** Rollback sem entender a causa pode mascarar corrupção de dados ou problema de segurança.
- **Comunicar muito cedo com informação incompleta.** Uma estimativa errada de "resolve em 10 min" que não se cumpre corrói confiança mais do que silêncio inicial.

## Fora de escopo desta nota

- On-call rotation e PagerDuty/OpsGenie — relevante quando houver equipe.
- SLA formal com usuários — para produto comercial.
- Chaos engineering como prática preventiva — spec separado.

## Próximo passo

Promover a Draft quando o primeiro runbook de incidente for escrito. Criar `docs/runbooks/incident-pod-crashloop.md` como primeiro exemplo concreto — é o cenário mais provável em Kubernetes.

## Referências

- [Google SRE Book — Incident Management](https://sre.google/sre-book/managing-incidents/)
- [PagerDuty Incident Response Guide](https://response.pagerduty.com/)
- [Blameless post-mortems — Etsy](https://www.etsy.com/codeascraft/blameless-postmortems/)