# DeepSeek UI

**Um ambiente desktop de desenvolvimento assistido por IA, com revisão de alterações e controle de acesso.**

![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white) ![PyQt6](https://img.shields.io/badge/Desktop-PyQt6-41CD52?logo=qt&logoColor=white) ![Selenium](https://img.shields.io/badge/Automação-Selenium-43B02A?logo=selenium&logoColor=white) ![CI](https://github.com/JackNoArms/deepseek_ui/actions/workflows/checks.yml/badge.svg)

> Projeto independente, não afiliado ao DeepSeek. Integra a interface web de chat.deepseek.com por automação do navegador do usuário; não utiliza uma API oficial.

## Por que este projeto existe?

Alternar constantemente entre chat, editor, arquivos e terminal interrompe o fluxo de desenvolvimento. O **DeepSeek UI** reúne essas etapas em um aplicativo Windows, mantendo o projeto aberto como contexto e permitindo revisar as modificações propostas antes de aplicá-las.

A jornada é simples: **conectar o navegador → abrir um projeto → descrever a tarefa → acompanhar as alterações → revisar e aplicar**.

## Prévia da experiência

| Celular — painel remoto | Desktop — painel remoto |
| --- | --- |
| ![Prévia do painel remoto no celular com dados fictícios](docs/screenshots/remote-mobile-demo.png) | ![Prévia do painel remoto no desktop com dados fictícios](docs/screenshots/remote-desktop-demo.png) |

*Prévia isolada do painel remoto, com conteúdo fictício e respostas de API simuladas. Não representa uma sessão real autenticada.* Confira os critérios de acessibilidade e os testes de interface em [UX do painel remoto](docs/UX-REMOTE.md).

## O que ele faz

- **Assistência com contexto:** abre projetos locais, lê arquivos autorizados e apresenta mudanças como diferenças revisáveis.
- **Dois modos de uso:** perguntas pontuais ou execução em várias rodadas no modo Agente.
- **Controle sobre arquivos:** permissões configuráveis, validação de caminhos e backups nas operações diretas de escrita.
- **Ferramentas integradas:** explorador de arquivos, terminal, histórico por projeto e anexos.
- **Acompanhamento pelo celular:** painel web local com chat, arquivos, fila e decisões, acessível por Tailscale Serve quando configurado.
- **Notas opcionais por projeto:** a aba **Vault** organiza notas locais. Essas notas são dados do usuário e **não estão incluídas neste repositório público**.

## Tecnologias e arquitetura

| Camada | Tecnologia | Responsabilidade |
| --- | --- | --- |
| Interface desktop | Python, PyQt6 | Conversa, projetos, diffs, confirmações e terminal |
| Navegador | Selenium, Chrome | Controle da sessão web autenticada |
| Execução | Python | Análise de respostas, ações, permissões e backups |
| Painel remoto | HTML, CSS, JavaScript | Interface responsiva e acessível no celular |
| Rede privada (opcional) | Tailscale Serve | Acesso remoto ao servidor HTTP local |
| Qualidade | Pytest, GitHub Actions | Testes de regressão e verificações no Windows |

A integração via Selenium depende da interface do site e pode precisar de manutenção quando o serviço mudar.

## Começando

**Pré-requisitos:** Windows, Python 3.10 ou superior e Google Chrome. O instalador automático do Chrome/driver e o comportamento da sessão dependem do ambiente.

1. Clone o repositório e entre na pasta do projeto.
2. Execute `executar_main.bat` para preparar o ambiente virtual e iniciar o aplicativo.
3. No aplicativo, conecte o navegador, faça login manualmente no site se necessário e abra a pasta de um projeto.

```powershell
git clone https://github.com/JackNoArms/deepseek_ui.git
cd deepseek_ui
.\executar_main.bat
```

Também é possível preparar e iniciar manualmente:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python main.py
```

As sessões e configurações individuais permanecem na máquina. Não compartilhe perfis do navegador, cookies, tokens ou arquivos de configuração local.

### Instalador

O código contém arquivos de suporte ao empacotamento em `instalador/`, mas **o build reproduzível do instalador ainda não foi validado nesta versão pública**: scripts de entrada citados em documentação antiga não estão disponíveis. Use a execução com Python acima até essa etapa ser concluída.

## Qualidade e testes

As verificações abaixo foram executadas no ambiente de desenvolvimento em **17/11/2026**:

| Verificação | Resultado |
| --- | --- |
| Pytest completo | 275 testes aprovados |
| Scripts de testes standalone | 764 verificações aprovadas |
| Smoke checks selecionados para CI | 79 testes aprovados |
| Testes de interface headless | 5 cenários aprovados, com dados simulados |

Para executar localmente:

```powershell
python -m pip install pytest
python -m pytest testes/ -q
python testes/rodar_tudo.py
```

O workflow [Python smoke checks](.github/workflows/checks.yml) executa uma seleção de testes em Windows. Os testes automatizados não substituem a validação manual com login real, celular físico ou instalador.

## Segurança: limites importantes

O aplicativo **não é um sandbox do sistema operacional**. Perfis automáticos podem executar comandos arbitrários e modificar arquivos além do escopo previsto, dependendo do comando executado. Use preferencialmente acesso restrito e confirmação humana; confira cada diff e comando antes de autorizar.

Os mecanismos de validação de caminhos e backup protegem operações diretas de arquivos feitas pelo aplicativo, **não** os efeitos indiretos de comandos executados no shell.

## Contribuição

Alterações seguem branches curtas, commits por mudança real, testes e Pull Requests com critérios de revisão. Consulte [CONTRIBUTING.md](CONTRIBUTING.md). Relatórios de problemas e sugestões de UX são bem-vindos.
