# Supply Chain Security — VEX, SLSA, COSIGN

**Date:** 2026-05-26  
**Status:** Idea  

## Contexto

Este doc é complemento direto de `2026-05-26-sbom.md`. Enquanto aquele cobre geração e escaneamento de SBOM, este cobre a camada acima: **atestar integridade, proveniência e exploitabilidade** — o que transforma um inventário passivo em evidência verificável de segurança.

Os três temas são independentes mas compõem um pipeline:

```
build → SLSA (prove how) → COSIGN (sign what) → VEX (clarify impact)
```

## VEX — Vulnerability Exploitability eXchange

### O que é

Documento que, para cada CVE relevante encontrado em um SBOM, declara explicitamente se o produto **é de fato afetável** e por quê. Resolve o problema de falsos positivos em scanners: uma dependência vulnerável pode não ser exercitada, pode ter mitigação em outro layer, ou a vulnerabilidade pode não se aplicar ao contexto de uso.

### Status de exploitabilidade (CSAF/CycloneDX)

| Status | Significado |
|---|---|
| `not_affected` | Produto contém o componente mas não é vulnerável (e.g., código path não alcançável) |
| `affected` | Produto é vulnerável — requer ação |
| `fixed` | Vulnerabilidade corrigida nesta versão |
| `under_investigation` | Análise em andamento |

### Formatos

- **CycloneDX VEX:** embutido no SBOM ou arquivo separado `.cdx.json`.
- **CSAF (Common Security Advisory Framework):** padrão OASIS, preferido por CERTs e grandes vendors.
- **OpenVEX:** formato minimalista mantido pelo projeto Sigstore.

### Ferramentas

- `vexctl` (Sigstore/Chainguard) — cria e verifica documentos OpenVEX.
- `grype` — consome VEX para suprimir falsos positivos automaticamente.
- `trivy` — suporta VEX no escaneamento.

### Aplicação no wasp-agent

Após `make scan-vulns` (do SBOM doc), criar `vex.json` declarando os CVEs não exploráveis nas dependências Python que aparecem mas não são exercitadas em runtime. Reduz ruído em pipelines futuros.

---

## SLSA — Supply chain Levels for Software Artifacts

### O que é

Framework de segurança (pronunciado "salsa") mantido pela OpenSSF que define **4 níveis de garantia de proveniência de build**. A ideia é atestar: *este artefato foi produzido por este processo, a partir destas fontes, sem adulteração*.

### Níveis

| Nível | Garantia | Requisito principal |
|---|---|---|
| **SLSA 1** | Proveniência existe | Build gera provenance document (quem buildou, quando, de quê) |
| **SLSA 2** | Proveniência autenticada | Build service hospedado (CI); provenance assinada pelo serviço |
| **SLSA 3** | Build hardened | Build isolado, sem acesso à rede/secrets durante build; fonte verificada |
| **SLSA 4** | Build hermético + revisão | Two-party review, build reproduzível, provenance verificável por terceiros |

A maioria dos projetos open source mira SLSA 2 ou 3. SLSA 4 é raro e caro.

### Provenance document

Arquivo JSON assinado que contém:

- `buildType`: tipo de build (GitHub Actions, etc.)
- `builder.id`: identidade do sistema de build
- `invocation.configSource`: URI do workflow + digest do commit
- `materials`: SHAs de todas as entradas (source repo, dependências)

### Ferramentas

- `slsa-github-generator` — GitHub Actions que gera e assina provenance automaticamente. Zero configuração para projetos Python.
- `slsa-verifier` — CLI para verificar um artefato contra seu provenance document.
- `ko` (para Go) / `buildpack` — builders com SLSA integrado.

### Aplicação no wasp-agent

SLSA 1 é trivial: adicionar step no CI que salva provenance JSON junto com o release. SLSA 2 requer CI hospedado com identidade verificável (GitHub Actions atende). Para projeto pessoal sem CI formal, documentar o processo de build manual como SLSA 0 por ora, e atingir SLSA 1 quando CI for adicionado.

---

## COSIGN — Assinatura Criptográfica (Sigstore)

### O que é

Ferramenta do projeto **Sigstore** (Linux Foundation) para assinar e verificar artefatos de software: imagens de container, arquivos binários, SBOMs, provenance documents. Usa infraestrutura de transparência (Rekor, Fulcio) para tornar assinaturas verificáveis publicamente sem gestão de chaves privadas.

### Modos de assinatura

**Keyless (recomendado):**
- Identidade OIDC do CI (GitHub Actions, GitLab, etc.) é usada como âncora de confiança.
- Fulcio emite certificado efêmero vinculado à identidade do workflow.
- Assinatura + certificado são registrados no Rekor (log de transparência imutável).
- Sem chaves privadas para gerenciar ou rotacionar.

**Key-based:**
- Par de chaves gerado localmente (`cosign generate-key-pair`).
- Chave privada protegida por senha ou KMS (AWS KMS, GCP KMS, HashiCorp Vault).
- Mais controle, mais responsabilidade.

### O que se assina

- **Imagens de container:** `cosign sign <image>@<digest>` — atesta que esta imagem foi produzida por este processo.
- **SBOMs:** `cosign attest --type spdx <image>` — anexa SBOM como attestation à imagem.
- **Arquivos arbitrários:** `cosign sign-blob <file>` — wheels Python, binários, configs.

### Verificação

```bash
cosign verify \
  --certificate-identity-regexp "^https://github.com/org/repo/.*" \
  --certificate-oidc-issuer "https://token.actions.githubusercontent.com" \
  <image>@<digest>
```

Verifica: assinatura válida + certificado emitido pelo Fulcio para a identidade OIDC esperada + entrada no Rekor.

### Rekor — log de transparência

Append-only, imutável. Toda assinatura feita via Sigstore é registrada. Permite:
- Auditoria: quem assinou o quê e quando.
- Detecção de compromisso: se uma assinatura aparecer no Rekor antes do build esperado, algo está errado.

### Aplicação no wasp-agent

Hoje: sem imagem de container, sem releases formais. COSIGN aplica quando:

1. **wasp-agent for distribuído como imagem:** assinar a imagem no CI com keyless COSIGN — adicionar um step `cosign sign` após o `docker push`.
2. **SBOM do agente:** assinar o `sbom.cdx.json` gerado por `syft` com `cosign sign-blob` — consumidores podem verificar que o SBOM não foi adulterado.
3. **Plataformas provisionadas:** assinar SBOMs dos workloads e commitar a assinatura junto no repo GitOps — auditabilidade completa da cadeia.

---

## Pipeline completo

```
source commit
    │
    ▼
CI build (GitHub Actions)
    │
    ├─ syft → sbom.cdx.json
    │         │
    │         └─ grype + vex.json → CVE report filtrado
    │
    ├─ slsa-github-generator → provenance.json
    │
    └─ cosign sign (keyless)
          ├─ assina imagem@digest
          ├─ attest sbom.cdx.json
          └─ attest provenance.json
              │
              └─ registrado no Rekor
```

Verificador downstream:
```
cosign verify-attestation --type spdx <image>   → SBOM verificado
slsa-verifier verify-artifact <image>           → proveniência verificada
```

## Conexão com outros specs

- **SBOM (`2026-05-26-sbom.md`):** este doc é a camada de integridade em cima do inventário.
- **EU AI Act / CRA (`2026-05-26-eu-ai-act.md`):** CRA exige evidência de supply chain security para produtos digitais na UE. SLSA + COSIGN são respostas diretas.
- **DORA Metrics (`2026-05-26-dora-metrics.md`):** CFR pode ser alimentado por detecção de comprometimento via Rekor (assinatura inesperada = possível incidente).

## Armadilhas

- **Confundir assinatura com integridade de conteúdo.** COSIGN atesta que *este processo* produziu *este artefato*. Não garante que o código é correto ou seguro.
- **Keyless sem entender o modelo de confiança.** Keyless delega confiança à identidade OIDC do CI — se a pipeline for comprometida, a assinatura ainda é válida. SLSA 3+ mitiga isso.
- **VEX sem processo de revisão.** Declarar `not_affected` sem análise real cria falsa sensação de segurança. Cada declaração precisa de justificativa rastreável.
- **SLSA como destino, não como jornada.** Ir de SLSA 0 para SLSA 3 de uma vez é difícil. Incrementar nível a nível.

## Fora de escopo desta nota

- SBOM de imagens base (alpine, distroless) — gestão de upstream.
- Policy enforcement via OPA/Gatekeeper (verificar COSIGN no admission controller do cluster).
- Integração com Sigstore para repositórios privados (Sigstore Enterprise).

## Próximo passo

Promover a Draft quando CI for adicionado ao projeto. Ação imediata de custo zero: documentar o processo de build atual como SLSA 0 (manual, sem provenance) para ter baseline explícita antes de melhorar.

## Referências

- [Sigstore / COSIGN](https://docs.sigstore.dev/cosign/overview/)
- [SLSA framework](https://slsa.dev/spec/v1.0/)
- [slsa-github-generator](https://github.com/slsa-framework/slsa-github-generator)
- [OpenVEX specification](https://github.com/openvex/spec)
- [Rekor — transparency log](https://docs.sigstore.dev/rekor/overview/)
- [CSAF standard](https://oasis-open.github.io/csaf-documentation/)