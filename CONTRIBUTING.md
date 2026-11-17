# Contribuindo com o DeepSeek UI

Este repositório representa a evolução **real** do projeto. Commits, testes e datas registram ações executadas; não reescrevemos a história para parecer que houve desenvolvimento em períodos anteriores.

## Fluxo de trabalho

1. Abra uma issue ou descreva claramente o problema, o comportamento esperado e o critério de aceite.
2. Crie uma branch curta a partir de `main`: `feat/<assunto>`, `fix/<assunto>`, `docs/<assunto>` ou `chore/<assunto>`.
3. Preserve o funcionamento atual; implemente uma alteração pequena e revisável.
4. Execute os testes relacionados à mudança e registre resultados verificáveis.
5. Faça commits por unidade lógica usando **Conventional Commits**: `feat:`, `fix:`, `docs:`, `test:`, `refactor:`, `chore:` e `ci:`.
6. Abra uma pull request com justificativa, evidências e impacto sobre usuário e segurança. Para alterações de UI, inclua capturas antes/depois sem dados privados.
7. Faça merge somente após revisão, CI e verificação de segredos. Evite force-push em branches compartilhadas.

## Como verificar localmente

```powershell
python -m pip install -r requirements.txt
python -m pip install pytest
$env:QT_QPA_PLATFORM = "offscreen"
python testes/rodar_tudo.py
python -m pytest testes/ -q
```

A suíte possui testes standalone e testes coletados por `pytest`. **Não** execute um arquivo standalone isolado como se fosse um teste pytest; use o agregador `rodar_tudo.py`. Alguns cenários E2E exigem Chrome, dependências nativas ou sessão de teste; registre como não executados quando for o caso.

## Segurança e privacidade

Nunca versione perfis de navegador, sessão, cookies, tokens, configurações locais, logs, backups, vault privado, dados de terceiros ou arquivos reais de clientes. Confira sempre `git status`, `git diff --cached --check` e `git diff --cached --name-only` antes do commit. Se um segredo aparecer, **revogue/rotacione primeiro**; apagar apenas o arquivo atual não remove o histórico.

O agente pode executar comandos e editar arquivos, dependendo do perfil de acesso. Testes e capturas devem usar dados fictícios; nada de contas de produção ou segredos em evidências.

## Critérios mínimos de aceite

- Comportamento ou documentação mudou de maneira comprovável.
- Testes pertinentes passaram (ou limitação justificada).
- Sem credenciais, dados pessoais ou artefatos gerados no commit.
- Documentação e notas locais atualizadas quando a decisão for durável.
- No caso de UX: estados vazios, erros, teclado, contraste e responsividade revisados.
