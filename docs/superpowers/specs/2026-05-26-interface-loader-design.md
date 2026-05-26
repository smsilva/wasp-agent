# InterfaceLoader Design

**Date:** 2026-05-26  
**Status:** Approved  
**Scope:** `wasp/clients/interfaces.py`, `main.py`

## Problem

`main.py` contém lógica de construção e configuração de interfaces agno misturada ao bootstrap da aplicação. Adicionar um novo canal (Slack, WhatsApp) exige modificar `main.py`.

## Solution

Classe `InterfaceLoader` em `wasp/clients/interfaces.py` que lê variáveis de ambiente e devolve a lista de interfaces configuradas. `main.py` passa a ter uma única linha de construção.

## API

```python
# main.py
from wasp.clients.interfaces import InterfaceLoader
interfaces = InterfaceLoader().build(agent)
```

## InterfaceLoader

```python
class InterfaceLoader:
    def build(self, agent) -> list:
        builders = [self._build_telegram]
        return [iface for b in builders if (iface := b(agent)) is not None]

    def _build_telegram(self, agent) -> Telegram | None:
        token = os.getenv("TELEGRAM_TOKEN")
        if not token:
            return None
        iface = Telegram(agent=agent, token=token)
        _install_start_token_handler(iface)
        return iface
```

## Extensibility

Para adicionar Slack: criar `_build_slack(agent) -> SlackInterface | None` e registrá-lo em `builders`. `main.py` não muda.

## Testing

- `_build_telegram` testado com `monkeypatch` em `TELEGRAM_TOKEN`
- `build` testado com mock de `_build_telegram` retornando `None` e não-`None`

## Files Changed

| File | Change |
|---|---|
| `wasp/clients/interfaces.py` | novo — contém `InterfaceLoader` |
| `main.py` | remove bloco de 6 linhas, adiciona 2 linhas (import + `InterfaceLoader().build(agent)`) |