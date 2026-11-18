# DeepSeek UI — revisão de UX/UI do painel remoto

**Data:** 17/11/2026
**Escopo:** painel web/PWA remoto (arquivos HTML, CSS e JS de src/), sem alterar autenticação ou permissões.

## História de uso

A pessoa inicia uma tarefa de programação no desktop e acompanha progresso, arquivos e decisões pelo celular. As decisões precisam ser compreensíveis e acionáveis mesmo em tela estreita, com teclado ou tecnologias assistivas. Quatro destinos: Chat, Projeto, Vault e Mais.

## Problemas e intervenções

| Antes | Depois | Evidência |
| --- | --- | --- |
| Abas dependiam só de classe visual | Semântica ARIA, controle de foco e seleção programática | Navegação por seta, Home e End no Chromium |
| Foco nem sempre explícito em campos | Contorno perceptível em textarea, select, input e abas | Teste de CSS e DOM |
| Composer apertado em tela pequena | Botões de 44 px e quebra de linha abaixo de 550 px | Em 390×844, sem rolagem horizontal; quatro controles visíveis |
| Feedback sem anúncio acessível | Região viva e alerta específico para erros | Teste de regressão |
| Movimento sem preferência do SO | Regra prefers-reduced-motion | Computed style: animation-duration=1e-05s |
| Leitura extensa em monitor largo | Largura de leitura controlada | Prévia desktop 1365×900 |

## Evidência executada

- JavaScript: node --check src/remote_panel.js — código de saída 0.
- Contratos existentes: pytest testes/test_remote.py testes/test_fila_decisao_remota.py -q — 43 passaram.
- Fluxo E2E headless no Playwright-Lab: cinco etapas, cinco passaram, com mapeamento inicial e capturas.
- Evidências locais (fora do Git): _backup-portfolio-20261117/pwa-evidencias/mapa/ e _backup-portfolio-20261117/pwa-evidencias/fluxo/.
- Capturas sanitizadas de demonstração: [mobile](screenshots/remote-mobile-demo.png) e [desktop](screenshots/remote-desktop-demo.png).

**Limites:** prévia isolada com o HTML, CSS e JavaScript reais, porém respostas de API e chat simulados. Não testamos conta real do DeepSeek, notificações reais, Tailscale ou instalação em celular físico. As imagens são exemplos fictícios, não provas de autenticação.

## Próximas melhorias

- Medir contraste e testar leitor de tela nos seis temas.
- Testar 320, 375, 768 e 1440 px com conversas e decisões controladas.
- Evoluir estados vazios e tratamento de erros por aba, com microcopy contextual.
- Auditar telas Qt do desktop separadamente.
- Registrar screenshots do aplicativo real somente após revisão de privacidade.

## Publicação

Não publicar perfil de navegador, sessões, tokens, cookies, backups, logs, vault ou conversas reais. O planejamento permanece no vault privado do projeto.
