# Prompt Versioning

**Date:** 2026-05-26  
**Status:** Idea  

## Contexto

O system prompt do `wasp-agent` define o comportamento do LLM: tom, restrições, quando pedir confirmação, como usar tools. Hoje ele está embutido como string no código Python. Mudanças no prompt mudam o comportamento do agente tão profundamente quanto mudanças no código — mas não recebem o mesmo tratamento: não há diff intencional, não há teste de regressão automático vinculado à mudança, não há rollback fácil.

O problema ficou explícito em `2026-05-20-llm-behavior-evaluation.md`: a instrução de confirmação adicionada em `1cdca61` entrou sem teste de regressão. Se o prompt regredir, `make test` passa — só o golden set perceberia.

## O que prompt versioning significa

1. **Rastreabilidade:** cada versão do prompt tem um identificador (hash ou semver).
2. **Testabilidade:** o golden set de cenários (`llm-behavior-evaluation.md`) roda contra a versão atual do prompt a cada mudança.
3. **Rollback:** é possível voltar para a versão anterior do prompt sem deploy de código.
4. **Auditabilidade:** dado um log de produção com `prompt_version: v1.3`, é possível reproduzir o comportamento exato.

## Opções de armazenamento

### Opção A — Arquivo versionado no repo (recomendado para início)

```
wasp/prompts/
  system.md          ← prompt atual
  system.v1.md       ← versões explícitas (ou via git tags)
```

O código carrega o prompt do arquivo:
```python
PROMPT_PATH = Path(__file__).parent / "prompts" / "system.md"
SYSTEM_PROMPT = PROMPT_PATH.read_text()
PROMPT_VERSION = hashlib.sha256(SYSTEM_PROMPT.encode()).hexdigest()[:8]
```

- **Prós:** diff natural no PR, histórico no git, zero infraestrutura extra.
- **Contras:** rollback requer novo commit; não permite mudança sem deploy.

### Opção B — Prompt em ConfigMap (Kubernetes)

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: wasp-agent-prompts
data:
  system.md: |
    Você é o wasp-agent...
```

Montado como arquivo no pod; `kubectl rollout restart` aplica novo prompt sem rebuild de imagem.

- **Prós:** rollback via `kubectl apply` do ConfigMap anterior; mudança sem novo deploy de imagem.
- **Contras:** prompt fora do controle de versão do código; difícil auditar qual prompt estava em prod em dado momento.

### Opção C — Prompt registry externo

Serviço como LangSmith, PromptLayer, ou Weights & Biases Prompts. Gerencia versões, A/B testing, métricas por versão.

- **Prós:** UI dedicada, A/B testing nativo, métricas por versão de prompt.
- **Contras:** dependência externa, custo, overkill para projeto pessoal.

**Recomendação para v1:** Opção A (arquivo no repo). Simples, rastreável, sem infra extra. Migrar para B se o ciclo de iteração de prompt ficar muito acoplado ao ciclo de deploy de código.

## Metadata de prompt

Cada execução deve logar:

```python
logger.info("llm_call", extra={
    "prompt_version": PROMPT_VERSION,   # hash do system.md
    "model": model_name,
    "tokens_in": usage.input_tokens,
    "tokens_out": usage.output_tokens,
})
```

Isso permite correlacionar comportamento com versão de prompt em produção.

## Testes vinculados ao prompt

O golden set de `llm-behavior-evaluation.md` deve rodar automaticamente quando `wasp/prompts/system.md` muda:

```yaml
# .github/workflows/prompt-eval.yml
on:
  push:
    paths:
      - 'wasp/prompts/**'
jobs:
  eval:
    steps:
      - run: make eval-golden-set
```

`make eval-golden-set` executa os cenários canônicos com o modelo de produção e falha se algum cenário regredir (tool call errada, confirmação ausente, etc.).

## Rollback de prompt

Com Opção A (arquivo no repo):
1. `git revert <commit-que-mudou-prompt>` — cria novo commit revertendo o prompt.
2. Deploy normal — nenhum procedimento especial.

Com Opção B (ConfigMap):
1. `kubectl apply -f prompts-configmap-v1.2.yaml`
2. `kubectl rollout restart deployment/wasp-agent`

## Versionamento semântico de prompt

Convenção sugerida (embutida como comentário no topo do `system.md`):

```markdown
<!-- prompt-version: 1.3.0 -->
<!-- major: mudança de comportamento ou persona -->
<!-- minor: nova instrução ou restrição -->
<!-- patch: correção de wording sem mudança de comportamento -->
```

MAJOR bump → obrigatório rodar golden set completo manualmente antes de produção.

## Conexão com outros specs

- **LLM behavior evaluation (`2026-05-20-llm-behavior-evaluation.md`):** este spec é o que define *o que* testar; prompt versioning é *quando* e *como* vincular o teste à mudança.
- **DORA Metrics (`2026-05-26-dora-metrics.md`):** mudança de prompt é um tipo de "deploy" — deve ser rastreada para CFR (regressão de comportamento = failure).
- **Observabilidade:** `prompt_version` como label em métricas Prometheus permite correlacionar degradação com versão de prompt.

## Armadilhas

- **Prompt embutido em f-string com variáveis.** Dificulta hash estável — partes dinâmicas (ex: nome do usuário) não devem estar no arquivo versionado. Separar template (versionado) de interpolação (runtime).
- **Mudança de prompt sem golden set.** A tentação é "só melhorei o wording". Comportamento do LLM é sensível a wording — sempre rodar ao menos o golden set básico.
- **Versão de prompt diferente entre ambientes.** ConfigMap em staging e prod podem divergir silenciosamente. Manter a versão como label no pod para auditoria.
- **Prompt longo sem estrutura.** Prompt difícil de ler é difícil de versionar e revisar. Usar seções com headers Markdown mesmo que o LLM não "veja" a formatação.

## Fora de escopo desta nota

- A/B testing de prompts em produção (split de tráfego por versão).
- Fine-tuning de modelo (categoria diferente de otimização).
- Prompt chaining (múltiplos prompts em sequência) — arquitetura separada.

## Próximo passo

Promover a Draft quando `2026-05-20-llm-behavior-evaluation.md` for promovido — os dois caminham juntos. Ação imediata: extrair o system prompt atual para `wasp/prompts/system.md` e adicionar o hash como campo de log.

## Referências

- [Prompt versioning patterns — Simon Willison](https://simonwillison.net/2023/Dec/31/ai-in-2023/)
- [LangSmith prompt hub](https://docs.smith.langchain.com/old/hub/dev-setup)
- [Semantic versioning](https://semver.org/)