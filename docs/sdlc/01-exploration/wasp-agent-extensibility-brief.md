# Spec Brief: Extensibilidade de Recursos do wasp-agent

> Documento de entrada para criação de spec via Claude Code.
> O objetivo deste brief **não é** definir a solução, mas dar contexto
> suficiente para que a spec final seja redigida com clareza de escopo
> e decisões justificadas.

---

## 1. Contexto

`wasp-agent` é um projeto pessoal de estudo sobre Agentes de IA aplicados
a operações de plataforma (Kubernetes, DevOps, Linux). A primeira versão
está funcional e implementa o seguinte fluxo:

```
Usuário Telegram  →  wasp_agent_bot  →  Agno Agent (LLM + tools)
                                              │
                                              ▼
                                        Pydantic model
                                              │
                                              ▼
                                        Render YAML (CR)
                                              │
                                              ▼
                              git commit em wasp-gitops/infrastructure/tenants/
                                              │
                                              ▼
                                       ArgoCD sync
                                              │
                                              ▼
                                Crossplane Composition aplica
                                              │
                                              ▼
                              ConfigMap (recurso de teste inicial)
                                              │
                                              ▼
                       wasp-agent responde ao usuário no Telegram com status
```

### Stack atual

- **Agno Framework** para orquestração do agente (modelo + tools).
- **Pydantic** para definição e validação de schemas dos Custom Resources.
- **wasp-gitops** (GitHub) como source of truth declarativo.
- **ArgoCD + Crossplane** consumindo o repositório.
- **Telegram Bot** como interface de entrada.

### Estado do código

Versão funcional em refactor. As tools do Agno hoje expõem métodos que
constroem objetos Pydantic e renderizam YAML. Toda a lógica de CRs vive
acoplada ao core do agente.

---

## 2. Problema

Como permitir que **novos Custom Resources** sejam adicionados ao
wasp-agent **sem modificar o core**, possibilitando que **times
diferentes** ofereçam seus próprios recursos provisionáveis via agente?

A extensibilidade pode ser:

- **Estática** — adicionar um recurso implica em redeploy do agente
  (aceitável).
- **Dinâmica** — recursos podem ser descobertos em runtime sem rebuild
  (desejável, não obrigatório no v1).

---

## 3. Abordagens em Consideração

Quatro abordagens foram avaliadas. Esta spec deve focar em **(1) e (3)**,
com **(4)** mencionada como exploração futura. A abordagem **(2) foi
descartada** (manifestos declarativos longos = manutenção difícil).

### 3.1. Abordagem 1 — Plugin via Python Entry Points  ✅ candidato

Cada tipo de recurso é um pacote Python instalável que registra um
`ResourceProvider` via `[project.entry-points."wasp_agent.resources"]`
no `pyproject.toml`. No boot, o wasp-agent faz
`importlib.metadata.entry_points()` e descobre os providers disponíveis.

Cada provider expõe:

- Modelo Pydantic (schema do CR).
- Método `render() -> str` ou template Jinja.
- Metadados (nome da tool, descrição para o LLM, exemplos).

**Prós**

- Python idiomático, zero mágica.
- Times mantêm seus próprios repositórios/pacotes.
- Lógica imperativa real (validações complexas, transformações) cabe
  naturalmente.
- Funciona localmente sem Kubernetes.
- Testabilidade: cada provider testa isoladamente como qualquer
  pacote Python.

**Contras**

- Incluir novo recurso exige rebuild da imagem do wasp-agent (redeploy).
- Acoplamento de versões: o agente precisa instalar cada plugin.

### 3.2. Abordagem 3 — Discovery via CRDs do Kubernetes  ✅ candidato (com ajuste)

O wasp-agent consulta a API do cluster por CRDs anotados (ex.:
`wasp.io/agent-exposed: "true"`), lê o OpenAPI schema do CRD, e gera
as tools dinamicamente via `pydantic.create_model()`.

**Restrição crítica:** a spec precisa contemplar **execução sem
Kubernetes disponível** (dev local, testes, ambientes onde os recursos
ainda não existem no cluster). A versão pura "fala com a K8s API"
inviabiliza isso.

**Variações possíveis a explorar na spec**

- **3a) Live cluster discovery** — para produção: agente lê CRDs em
  runtime via API K8s.
- **3b) Filesystem discovery** — carrega definições de CRD a partir de
  arquivos locais (`crds/*.yaml`), idêntico ao formato Kubernetes mas
  sem precisar do cluster.
- **3c) Git-backed discovery** — agente lê CRDs diretamente de um
  caminho no `wasp-gitops` (ou outro repo), via clone/pull periódico.
  Mantém o GitOps puro e funciona sem cluster.

**Prós**

- Source of truth alinhado com o ecossistema Kubernetes-native.
- Adicionar recurso = commit Git (modo 3c) ou criar CRD (modo 3a).
- Sem redeploy do agente.

**Contras**

- Schema OpenAPI dos CRDs é menos expressivo que Pydantic puro
  (lógica de validação customizada fica difícil).
- Descrições para o LLM precisam vir de annotations ou de um CRD
  auxiliar (`AgentTool` próprio?).
- Hot-reload exige supervisor/watch.

### 3.3. Abordagem 4 — MCP Servers por time  🔭 exploração futura

Cada time roda seu próprio MCP server. wasp-agent é cliente MCP
multi-server.

**Fora do escopo desta spec.** Mencionar apenas como direção futura,
deixando hooks na arquitetura que não inviabilizem a migração depois
(ex.: o `ResourceProvider` poderia, no futuro, ser um adapter para
chamadas MCP em vez de execução in-process).

---

## 4. Direção Preliminar a Validar

Hipótese de trabalho a ser confirmada ou rejeitada pela spec:

> **(1) e (3) não são alternativas — são camadas complementares.**
>
> - **(1) define o contrato interno** (`ResourceProvider`): como o core
>   enxerga um recurso, independente de onde a definição veio.
> - **(3) é uma fonte adicional** de providers, ao lado dos entry points
>   Python, que materializa schemas vindos de CRDs em providers
>   conformes ao mesmo contrato.

Estrutura conceitual:

```
                ┌──────────────────────────────────┐
                │       ResourceRegistry           │
                │  (contrato único: provider API)  │
                └─────────────────┬────────────────┘
                                  │
            ┌─────────────────────┼──────────────────────┐
            │                     │                      │
   ┌────────▼────────┐  ┌─────────▼──────────┐  ┌────────▼─────────┐
   │ EntryPointLoader│  │ CrdFilesystemLoader│  │ CrdClusterLoader │
   │   (abordagem 1) │  │   (abordagem 3b)   │  │  (abordagem 3a)  │
   └─────────────────┘  └────────────────────┘  └──────────────────┘
```

Loaders são plugáveis e configuráveis. Ambiente dev usa
`EntryPointLoader` + `CrdFilesystemLoader`. Produção pode somar
`CrdClusterLoader`.

---

## 5. Requisitos e Restrições

### Funcionais

- Adicionar recurso novo **não** deve exigir alteração no core do
  wasp-agent.
- Adicionar recurso novo **deve** poder ser feito com redeploy
  (aceitável). Hot-reload é nice-to-have.
- Cada recurso deve poder expor **N tools** (criar, consultar, atualizar,
  deletar — não apenas criar).
- Cada tool precisa fornecer metadados ricos para o LLM (descrição,
  exemplos, parâmetros tipados).
- O fluxo de commit em `wasp-gitops` deve ser **reutilizável** entre
  providers (não reimplementado por cada um).

### Não funcionais

- **Funcionar sem Kubernetes** em modo dev/teste.
- Continuar Python/Agno/Pydantic.
- Manter GitOps-first.
- Cada provider deve ser **testável isoladamente**.
- Não inviabilizar futura migração para MCP (abordagem 4).

### Fora de escopo

- Autenticação/autorização por recurso (deixar para spec futura).
- Multi-tenancy do próprio agente.
- Workflow de aprovação para criação de recursos.

---

## 6. Questões em Aberto para a Spec Decidir

A spec final deve responder, no mínimo:

1. **Contrato do `ResourceProvider`**: quais métodos/atributos?
   Pydantic model + render? Ou algo mais rico (lifecycle hooks,
   validação custom, status query)?
2. **Empacotamento de plugins**: monorepo com namespace packages?
   Repos separados? Como versionar?
3. **Formato dos metadados para o LLM**: docstrings? Decorator com
   argumentos? Annotations no Pydantic? Como manter sincronizado?
4. **Loaders**: como configurar quais loaders estão ativos?
   Variáveis de ambiente? Arquivo de config? Auto-detect?
5. **Conflito de nomes**: e se entry point e CRD definirem recursos
   homônimos? Quem ganha?
6. **Operações além de criar**: como cada provider declara as
   operações que suporta? Como o agente as expõe como tools distintas
   no Agno?
7. **Reuso do commit no gitops**: API/helper compartilhado? Onde vive?
8. **CRDs sem cluster (3b/3c)**: qual o formato de pasta? `crds/*.yaml`?
   `resources/*/crd.yaml`? Como carregar metadados extras (descrição,
   exemplos) que não cabem no CRD?
9. **Hot-reload**: in scope para v1 ou v2?
10. **Caminho de migração para MCP**: o `ResourceProvider` precisa
    sustentar um futuro `MCPProvider` adapter sem refactor doloroso?

---

## 7. Material de Referência

### Repositórios envolvidos

- `wasp-agent` — código do agente (Python, Agno).
- `wasp-gitops` — manifests aplicados por ArgoCD; pasta
  `infrastructure/tenants/` recebe os CRs.

### Decisões já tomadas

- Abordagem **(2)** descartada — manifestos declarativos puros (YAML
  com schema embutido + template) por dificuldade de manutenção quando
  os arquivos crescem.
- Abordagem **(4)** adiada — explorar depois do v1 da extensibilidade
  estar provada.

### Estado de implementação

- v0 funcional: cria `Platform` (kind único) com commit no gitops,
  feedback via Telegram.
- Refactor em andamento no código Python; momento bom para introduzir
  o contrato de provider antes de adicionar o segundo tipo de recurso.

---

## 8. Entregáveis Esperados da Spec

A spec gerada a partir deste brief deve produzir:

1. **Decisão arquitetural**: confirmação ou rejeição da hipótese da
   seção 4, com justificativa.
2. **Definição do contrato `ResourceProvider`** com tipos e exemplos.
3. **Estrutura de diretórios** do core e de um provider de exemplo.
4. **Estratégia de packaging** (monorepo vs polirepo, namespace
   packages, versionamento).
5. **Plano de migração** do código atual (Platform hardcoded) para o
   novo modelo.
6. **Roadmap incremental** em fases: o que entra no v1, v2, v3.
7. **Lista de não-decisões** explícitas — coisas que ficaram fora para
   evitar overengineering.

### Estilo da spec

Preferência por **spec curta e focada**, no estilo OpenSpec. Evitar
documento monolítico. Se fizer sentido, quebrar em specs
domínio-específicas (provider contract, loader strategy, gitops
helper, etc.).
