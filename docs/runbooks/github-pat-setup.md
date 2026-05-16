# GitHub PAT — Setup

Como criar o fine-grained Personal Access Token para que o bot possa commitar no `smsilva/wasp-gitops`.

---

## 1. Criar o PAT

1. Acesse https://github.com/settings/personal-access-tokens/new
2. Preencha:
   - **Token name**: `wasp-agent-gitops` (ou similar)
   - **Expiration**: 90 dias (renove antes do vencimento)
   - **Resource owner**: sua conta ou org dona do repo
3. Em **Repository access**, selecione **Only select repositories** → `smsilva/wasp-gitops`
4. Em **Permissions → Repository permissions**, conceda:
   - **Contents**: `Read and write`
   - Todas as demais: `No access`
5. Clique em **Generate token** e copie o valor exibido (ele não será mostrado novamente).

---

## 2. Adicionar ao `.env`

```
GH_PAT=github_pat_...
```

---

## 3. Verificar

```bash
source .env
curl -s -H "Authorization: Bearer ${GH_PAT}" \
  https://api.github.com/repos/smsilva/wasp-gitops \
  | python3 -m json.tool | grep '"full_name"'
```

Resposta esperada:
```json
"full_name": "smsilva/wasp-gitops",
```

Se retornar `404` ou `401`, verifique se o PAT tem escopo correto e se o repo está selecionado.

---

## Renovação

O PAT expira na data configurada. Para renovar: acesse https://github.com/settings/personal-access-tokens, localize o token e clique em **Regenerate**.