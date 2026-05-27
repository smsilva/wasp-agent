# Exploração: Reutilização de conhecimento arquitetural entre projetos

**Date:** 2026-05-26  
**Status:** Idea

## Problema

`wasp-agent` está acumulando um corpo de conhecimento arquitetural valioso: DORA Metrics, EU AI Act, SBOM, Supply Chain Security, SonarQube, Snyk, observabilidade, telemetria, multi-channel, GitOps. Esse conhecimento está disperso em design docs, CLAUDE.md e specs — inacessível quando um novo projeto começa do zero com Claude Code.

## Pergunta a responder

Qual a forma mais eficaz de tornar esse conhecimento reutilizável em projetos futuros, sem acoplá-lo ao wasp-agent?

## Opções em aberto

**A) Skills específicas por domínio**  
Criar skills como `observability-setup`, `gitops-pattern`, `supply-chain-security` em `~/.claude/skills/`. Vantagem: ativadas sob demanda em qualquer projeto. Desvantagem: manutenção distribuída.

**B) Templates de design docs**  
Repositório ou pasta `~/git/linux/claude/templates/` com esqueletos de architecture docs para temas recorrentes (DORA, SBOM, multi-channel). Vantagem: baixo overhead. Desvantagem: não se integra ao fluxo do agente.

**C) Checklist arquitetural de onboarding**  
Skill `project-init` que o agente aplica ao iniciar projetos novos — pergunta sobre canais, observabilidade, GitOps, segurança e gera estrutura inicial. Vantagem: ponto de entrada único. Desvantagem: mais complexo de manter atualizado.

**D) CLAUDE.md global com padrões cross-project**  
Expandir `~/.claude/CLAUDE.md` com seções de padrões arquiteturais reutilizáveis. Vantagem: sempre presente. Desvantagem: polui instruções gerais com contexto específico de domínio.

## Próximo passo sugerido

Antes de criar artefatos, validar: quais temas do wasp-agent têm maior chance de reaparecer em projetos futuros? DORA + observabilidade + multi-channel parecem os candidatos mais fortes. Começar com uma skill por domínio (opção A) e avaliar o atrito antes de expandir.
