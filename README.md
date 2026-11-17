# DeepSeek UI

**Um ambiente de desenvolvimento assistido por IA, feito em Python, com controle humano sobre alterações no código.**

![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white) ![Qt](https://img.shields.io/badge/Desktop-PyQt6-41CD52?logo=qt&logoColor=white) ![Selenium](https://img.shields.io/badge/Browser-Selenium-43B02A?logo=selenium&logoColor=white)

> Projeto independente de integração com o **chat.deepseek.com** por automação de navegador. Não é um cliente oficial do serviço. Utiliza a sessão autenticada pelo usuário; não necessita de chave de API.

## O problema e a solução

Trocar de janela entre o chat de IA e o editor interrompe o contexto de programação. O DeepSeek UI reúne a conversa e o workspace em uma interface desktop: abre arquivos, acompanha o projeto, propõe diferenças (*diffs*) e permite revisar o que será gravado. O modo Agente pode trabalhar em várias rodadas com permissões configuráveis.

**Jornada principal:** conectar a sessão → abrir projeto → explicar a tarefa → analisar propostas e resultados → aplicar mudanças autorizadas.

### Destaques de engenharia

- **Python + PyQt6:** interface desktop, gerenciamento de arquivos, histórico e terminal integrado.
- **Automação com Selenium:** integração via navegador autenticado, sem chave de API.
- **Segurança por escopo:** perfis de acesso, validação de caminhos e backup nas edições de arquivos; ações de comando dependem do perfil configurado.
- **Painel mobile:** PWA local acessível por Tailscale Serve, com decisões, fila e acompanhamento de tarefas.
- **Qualidade:** testes automatizados para núcleo, permissões, integrações e componentes de interface.

**Segurança:** perfis amplos/automáticos e execução de comandos podem modificar arquivos e executar programas. Utilize o perfil mais restritivo compatível com sua necessidade; nunca publique `chrome_profile/`, `.deepseek_ui/`, `config.json` ou segredos.

**Situação:** código-fonte local versionado em 17/11/2026. Na validação de referência, `testes/rodar_tudo.py` teve 764 casos corretos e `pytest testes/ -q` teve 271 testes aprovados. Isso não substitui testes manuais com conta, navegador e instalador reais.

## Instalar

Dois cliques em `executar_main.bat`. Na primeira vez ele acha um Python 3.10+
(oferece instalar pelo `winget` se não houver), cria o `.venv` e instala o
`requirements.txt`; depois só reinstala quando o `requirements.txt` mudar.
`executar_main.bat --preparar` só prepara e sai.

À mão, se preferir:

```
pip install -r requirements.txt
```

Precisa do **Google Chrome**. O driver o Selenium 4 baixa sozinho; sem Chrome
instalado, o Selenium Manager baixa o Chrome for Testing.

### Versão instalada (sem Python)

`DeepSeekUI-Setup-<versão>.exe` instala por usuário, sem pedir administrador,
em `%LOCALAPPDATA%\Programs\DeepSeek UI`, com atalho no menu Iniciar (e na
área de trabalho, se marcar). Se não achar o Chrome, oferece instalar pelo
`winget`; o Tailscale (para o celular) é uma caixa opcional.

A versão instalada grava os dados em `%LOCALAPPDATA%\DeepSeek UI` (config,
`chrome_profile/` com o login, token do painel remoto, chaves de push e
`logs/deepseek_ui.log`). Na primeira vez ela oferece **trazer login,
pareamento do celular e configurações** de uma cópia do código-fonte que você
já usa — nada é apagado na cópia. Ao desinstalar, pergunta se apaga esses
dados (padrão: manter).

### Gerar o instalador

> **Limitação verificada na preparação do repositório (17/11/2026):** esta cópia de código-fonte não contém `build.bat` nem `requirements-build.txt`, mencionados originalmente na documentação. O processo de empacotamento abaixo descreve o fluxo previsto, mas precisa ter seus scripts de entrada reconstruídos e validados antes de ser considerado reproduzível.

```
build.bat  # pendente de restauração/validação nesta cópia
```

Prepara o `.venv`, instala o PyInstaller (`requirements-build.txt`), empacota
em `dist\DeepSeekUI\` (`instalador\deepseek_ui.spec`), roda o **autoteste** no
`.exe` empacotado e só então monta `dist\instalador\DeepSeekUI-Setup-<versão>.exe`
com o Inno Setup (`instalador\deepseek_ui.iss`; instalado pelo `winget` se
faltar). Se o autoteste falhar, o instalador não é gerado. A versão vem de
`src/__version__.py`.

**Qual arquivo usar:** `dist\instalador\DeepSeekUI-Setup-<versão>.exe` para
instalar, ou `dist\DeepSeekUI\DeepSeekUI.exe` para rodar sem instalar. O
`build\pyinstaller\…\DeepSeekUI.exe` é rascunho do PyInstaller, não roda
sozinho ("Failed to load Python DLL") e o `build.bat` apaga essa pasta no fim.

`DeepSeekUI.exe --verificar` abre a janela, confere recursos do pacote,
plataforma da janela, shell do agente, painel do celular e Chrome pelo
Selenium (`src/autoteste.py`, inclusive um envio real de texto com quebras de
linha do Windows), grava o resultado no log e sai com o número de falhas
(0 = tudo certo). `--sem-chrome` pula o Chrome.

`instalador\testar_instalador.ps1 -Anterior <versão> -Atual <versão>` testa o
instalador na tela real: instala a anterior, atualiza para a atual, roda o
autoteste do instalado, abre pelo atalho, confere primeira e segunda execução e
desinstala. Recusa rodar se o DeepSeek UI estiver instalado de verdade (mesmo
AppId).

## Rodar

```
python main.py
```

1. **Conectar** — abre um Chrome controlado no chat.deepseek.com.
2. Na primeira vez o site cai no login. A UI avisa e **mantém o navegador
   aberto**: entre na conta e clique em Conectar de novo. O perfil fica em
   `chrome_profile/`, então depois disso já entra logado.
3. **Abrir pasta** — escolhe a raiz do projeto e reabre a conversa daquele
   projeto.
4. **Abrir vault** — vincula a pasta de notas Obsidian ao projeto. O vínculo e a
   conversa são específicos daquela pasta e continuam salvos entre execuções.
5. **Acesso** — escolhe entre projeto com confirmação, permissões CRUD por
   pastas escolhidas, projeto/vault automático, computador inteiro com
   confirmação ou computador inteiro automático.
6. Peça o que quer. `Enter` envia, `Shift+Enter` quebra linha, **`Ctrl+V` anexa**
   print de tela, imagem ou arquivo copiado do Explorer.

Não feche o Chrome controlado enquanto usa a UI — é por ele que tudo passa.

### Rodar mais de uma instância

Cada cópia do projeto (uma pasta diferente) tem o seu `chrome_profile/` e o
seu `.deepseek_ui/session.json`. Isso significa que **duas cópias rodam em
paralelo** sem briga — cada uma com sua janela, seu login e sua conversa. Duas
**instâncias da mesma pasta** não funcionam: o Chrome recusa o segundo
arranque porque o `--user-data-dir` já está em uso. A prova está em
`testes/test_multiplas_instancias.py`. A versão instalada tem os dados em
`%LOCALAPPDATA%\DeepSeek UI` e roda em paralelo com as cópias do código-fonte.

## Continua de onde você parou

Cada pasta tem a sua conversa do DeepSeek, guardada em
`.deepseek_ui/session.json`. Ao abrir o app no dia seguinte ele **reabre a última
pasta, conecta sozinho e volta para a conversa daquele projeto**, com o histórico
carregado — o modelo mantém tudo que já sabe do seu código.

Trocar de pasta troca de conversa. **Nova conversa** envia `Ctrl+J` ao DeepSeek
(com clique no controle do site como fallback), limpa o histórico local somente
quando o site confirma a troca e desgruda a conversa antiga; a próxima resposta
gruda a nova. O botão fica bloqueado enquanto há envio ou mensagens na fila.

Não quer que conecte sozinho? Ponha `"auto_conectar": false` no `.workspace.json`.

## Terminal

`Ctrl+`` abre um terminal na raiz do projeto, para olhar a pasta ou rodar algo
sem sair para o Explorer. É um shell normal, com `cd` funcionando e histórico nas
setas.

Sem trava nenhuma — quem digita é você, na sua máquina. Os comandos que o
*modelo* pede passam pelo `runner.py` (confirmação conforme o perfil de
Acesso); a Kitty não tem acesso a este painel.

## Painel remoto e controle pelo celular

Ver o que está acontecendo e **fazer tudo pelo celular**, de qualquer lugar.
O app sobe um servidor HTTP mínimo em `127.0.0.1:8765`; o
[Tailscale Serve](https://tailscale.com/kb/1242/tailscale-serve) encaminha essa
porta para a sua tailnet, com HTTPS e certificado automáticos. **Nada é exposto
à internet aberta** — só aparelhos da sua tailnet alcançam.

### Ligar (uma vez por máquina)

A primeira vez é manual, porque `tailscale serve` exige Administrador e
habilitar o recurso na conta:

1. Instale o Tailscale no PC e no celular, logados na mesma conta.
2. Acesse o link que o próprio `tailscale serve` imprime na primeira tentativa
   (`https://login.tailscale.com/f/serve?node=...`) e habilitar o Serve para a
   tailnet.
3. Rode `configurar_tailscale.bat` **como Administrador**. O `.bat` aponta o
   Serve e mostra a URL final.

Nas próximas vezes, ou para reiniciar depois que o app já está aberto, use o
botão **Remoto** no header: ele mostra o link, copia, e dispara o `.bat` elevado
quando necessário.

No celular, abra a URL do Tailscale com o token na primeira vez
(`.../?token=...`); o painel guarda em cookie e não pede mais.

### O que dá para fazer

- **Ver estado** — projeto aberto, status da última operação, agente rodando,
  fila de mensagens.
- **Chat** — enviar pergunta ao DeepSeek, ver a resposta em streaming, o agente
  trabalhando rodada a rodada.
- **Responder decisão** — o card aparece **no fim da aba Chat**, logo abaixo da
  última mensagem, com a mesma recomendação do PC. Clicar numa opção destranca
  o agente. Primeiro a responder vence; o outro lado é marcado como resolvido.
- **Trocar projeto** — lista das pastas recentes, ou navegador de pastas.
- **Trocar vault** — idem, com bootstrap do vault novo.
- **Ler, editar, criar, apagar** arquivo e pasta do projeto e do vault — o
  backup do `WorkspaceStore` protege cada gravação.
- **Buscar** — mesmo `Project.buscar` do agente, com filtro de pasta e extensão.
- **Anexar arquivo ou imagem** — pelo botão **📎 Anexar** (abre câmera/galeria
  no celular). O chip aparece no painel **e no composer do PC**; enviar a
  mensagem usa o anexo exatamente como se você tivesse colado no PC.
- **Colar da área de transferência** — pelo botão **📋 Colar**
  (`navigator.clipboard.read()`, único caminho no iOS Safari) ou pelo gesto
  nativo de colar do sistema quando o clip contém imagem/arquivo.
- **Notificações push** — o card de decisão dispara um push Web (VAPID).

### Quando o PC está ocupado

Se um diálogo modal estiver aberto no PC (Revisão, Acesso, etc.), a fila do Qt
trava. O servidor espera no máximo **5s** e devolve `app_ocupado` — o painel
mostra *"App ocupado no PC — feche o diálogo e tente de novo"* em vez do genérico
"Falha: app_ocupado", e a requisição HTTP retorna em vez de pendurar por minutos.

Na direção contrária, quando o celular faz uma ação (abrir projeto, gravar
arquivo, enviar mensagem, anexar), o PC **avisa no chat**: aparece uma linha
`↗ celular: gravou src/foo.py`, e o status do topo muda por 2,5s. Comandos de
polling (state, chat, árvore, browse) são excluídos — não inundam o chat.

### Android

Funciona direto no Chrome. Toque em "Ativar notificações" no painel e aceite a
permissão do navegador. Notificações chegam pelo serviço de push do Google.

### iPhone

A Apple só entrega Web Push para **apps adicionados à Tela de Início** (iOS
16.4+). O fluxo é:

1. Abra o painel no **Safari** (não funciona em navegadores de terceiros no iOS).
2. Toque em **Compartilhar** → **Adicionar à Tela de Início**.
3. Abra o painel pelo **ícone criado** (não pelo Safari).
4. Toque em "Ativar notificações" — agora o botão aparece; antes disso o painel
   mostra a instrução em vez do botão.

Sem o ícone, o painel funciona para ver, editar e enviar; só as notificações
push ficam indisponíveis, e o app avisa na tela.

### Cache do painel no Safari/PWA

O Safari dentro do PWA tem cache HTTP próprio, agressivo — já escondeu
mudanças por horas. Três defesas ao mesmo tempo:

- **Service Worker network-first** — toda requisição tenta a rede primeiro; o
  cache só serve de fallback offline. Na instalação, caches antigos são
  limpos.
- **`Cache-Control: no-store` em toda resposta** do servidor HTTP.
- **HTML versiona os estáticos** por `?v=N` (CSS, JS, manifest e ícones). Ao
  mexer num estático, sobe o número.

### Segurança

O token em `.deepseek_ui/remote_token` **autoriza escrita no disco** dentro do
sandbox do projeto. Quem pega o celular desbloqueado (ou lê o arquivo no PC)
pode escrever arquivo. Salvaguardas que continuam valendo pelo celular:

- **Sandbox de caminho** — `..`, rede, ADS, nome reservado, symlink recusados.
- **Backup antes de sobrescrever** — o `WorkspaceStore` mantém o comportamento.
- **`/api/browse` só lista pastas** — não é shell de filesystem.
- **Comandos só pelo agente** — o `runner.py` é disparado só pelo agente no PC;
  não há rota `/api/run`.
- **Terminal** — continua só no PC; não existe caminho web.

O detalhe da decisão está em
`vault/Decisões/ADR-013 Painel remoto via Tailscale Serve.md` (base) e
`vault/Decisões/ADR-015 Controle remoto total.md` (escopo completo).

## Os dois modos

**Pergunta e resposta** (Agente desligado). Uma pergunta, uma resposta. Se vier
código com arquivo marcado, aparece um card **Revisar e aplicar**.

**Agente** (chip ligado). A Kitty lê arquivos sozinha, trabalha em várias rodadas
e para quando termina. Por padrão, cada leitura, listagem ou busca pede
autorização antes de compartilhar o resultado com o DeepSeek; isso pode ser
alterado em **Acesso**. Nos perfis com confirmação, escrita e comando passam por
você. O perfil automático aplica alterações sem confirmação, mas mantém backup,
validação de caminho e bloqueio de pastas críticas nas ações de arquivo.
Comandos rodam num shell completo, sem lista de permitidos. Teto de 12 rodadas
e botão **Parar**, que também encerra um comando em execução.

No perfil **Pastas escolhidas**, cada grant é uma autorização explícita e não
abre uma segunda confirmação para aquela operação. Para uma nota nova, marque
**Criar** na pasta do vault; para alterar uma nota existente, marque **Editar**.
Operações sem grant continuam bloqueadas. Comandos executam sem confirmação,
num shell completo, com a raiz do projeto como diretório de trabalho. Os
grants não confinam os efeitos dos processos: um comando pode acessar outros
caminhos. A confirmação para compartilhar leituras é separada e pode ser
desligada em **Acesso**.

Se você enviar mensagens enquanto o DeepSeek ou o Agente estiver ocupado, elas
entram numa fila FIFO: o indicador mostra quantas aguardam e o app envia uma por
vez, na ordem. Projeto, permissões, formato e navegação de conversa ficam
bloqueados até a fila esvaziar para não mudar o contexto de mensagens
pendentes. Anexos são preservados na fila e enviados no primeiro turno do modo
Agente. Clique no chip de um anexo para abrir a prévia da imagem ou do texto.

## Controles

| Controle | O que faz |
|---|---|
| **Conectar / Desconectar** | Abre ou fecha o Chrome controlado |
| **● DeepThink** | Raciocínio longo. Deixa cada rodada bem mais lenta |
| **● Search** | Busca na web (desabilita quando a página não oferece) |
| **● Agente** | Liga o loop de várias rodadas |
| **Abrir pasta** | Define a raiz autorizada (fica salva) |
| **Acesso** | Configura o escopo e as permissões por projeto |
| **Remoto** | Abre o diálogo do painel remoto (link, copiar, ativar serve) |
| **Abrir vault** | Vincula o vault Obsidian ao projeto |
| **Retorno** | Seleciona Markdown (legado), JSON ou XML para o projeto |
| **Testar formato** | Faz uma sonda na conversa aberta; valida e contabiliza sem executar a ação |
| **Anexar** | Escolhe arquivos pelo diálogo (o mesmo que `Ctrl+V`) |
| **Nova conversa** | Envia `Ctrl+J` ao DeepSeek, zera o contexto e reenvia as regras |
| **Conversas** | Abre uma conversa da barra lateral e recarrega o histórico |
| **Terminal** | Mostra/esconde o terminal (`Ctrl+``) |
| **Explorer** | Abre a pasta do projeto no gerenciador de arquivos |
| **Parar** | Interrompe o agente no fim da rodada atual |

Os chips espelham a página de verdade: mexeu no DeepThink direto no Chrome, a UI
acompanha em ~2s.

## Projeto e vault

Ao abrir um projeto sem vault vinculado, o app cria `vault/` dentro dele e
vincula essa pasta automaticamente. O bootstrap não sobrescreve notas
existentes: cria o índice central `00 - Índice.md`, `AGENTS.md`, convenções,
categorias e modelos ausentes. **Abrir vault** permite escolher uma pasta
Obsidian externa.

As árvores **Projeto** e **Vault** permitem criar, editar e excluir arquivos e
pastas; exclusões são movidas para backup. No Vault, **Nova nota** abre um
formulário com tipo, título, tags, contexto e conteúdo, gerando frontmatter YAML
com datas ISO. O DeepSeek recebe as regras do vault e seu índice no início de
cada conversa. Para cada pedido, deve avaliar se há conhecimento durável que
mereça registro; as notas propostas devem ter contexto e data,
links internos úteis e conteúdo verificável, sem registrar cada detalhe
transitório.
Em **Acesso**, o perfil **Projeto + vault vinculado (automático)** dispensa
cliques para leitura, criação, edição e exclusão, mas só dentro do projeto e do
vault escolhido; alterações mantêm backups e comandos ainda pedem confirmação.
O perfil padrão continua pedindo revisão. O computador automático é mais amplo
e executa qualquer comando sem confirmação; a confirmação de leitura é
configurável separadamente nesse perfil.

## Protocolos de resposta

**Markdown/`kitty`** continua como padrão. Em **Retorno**, escolha JSON ou XML
para salvar a preferência daquele projeto; essa escolha pode ser feita mesmo
com o DeepSeek desconectado e vale para o próximo envio. Enquanto JSON/XML
estão sendo recebidos, a UI mostra apenas um indicador. Só depois da validação
renderiza texto e cards; respostas estruturadas inválidas mostram um aviso
amigável, nunca o JSON/XML cru. Nesses modos, o modelo devolve um único bloco
de código `json`/`xml` com um envelope de resposta:

```json
{
  "response": "Texto normal que aparece na conversa.",
  "actions": [
    {
      "action": "create",
      "path": "src/exemplo.py",
      "code": "print('Olá')"
    }
  ]
}
```

O campo `response` é exibido como texto normal; o código de cada ação de
criação/edição aparece em um card de código. `actions` é uma lista extensível:
cada item usa `action` como discriminador e os argumentos próprios daquela
operação (`path`/`code`, `command`, `term` etc.). Assim, novas operações não
precisam inventar chaves de topo como `nameCreate`. A validação estrita ocorre
antes de qualquer plano; resposta inválida não gera ação executável. XML segue
o mesmo contrato (`<response><text>…</text><actions>…</actions></response>`) e
usa CDATA para código/comandos. XML cru é recusado porque o renderizador do
site pode colapsar suas quebras de linha; o protocolo XML só é aceito dentro
de fence.

Quando houver uma dúvida importante, o DeepSeek pode emitir uma ação
`decision` com a pergunta e de 2 a 5 opções. O aplicativo mostra um card de
decisão no chat; no modo Agente, a execução pausa até a escolha, e nos demais
modos a escolha é enviada como continuação da conversa. O protocolo Markdown
usa um bloco `text` com `# kitty: acao=decidir` e os campos `question` e
`options`; JSON e XML usam, respectivamente, a ação `decision` e seu elemento
equivalente. A instrução inicial de cada conversa orienta o modelo a levantar
o escopo, planejar, implementar, testar e só concluir após as verificações.
O editor de arquivos também usa tema escuro e fonte monoespaçada para melhorar
a leitura de Markdown, JSON, XML e outros textos.

O histórico do `ChatPanel` guarda o **texto amigável** — em modo JSON/XML, é o
`response`, não o envelope cru. Isso evita que o painel remoto receba `{...}`
como se fosse resposta.

**Testar formato** envia uma ação controlada para um arquivo de teste, mas a UI
intercepta a resposta antes do executor e nunca cria esse arquivo. O contador
JSON/XML por projeto mostra quantas sondas corresponderam ao schema e ao conteúdo
esperado. Essa taxa compara a aderência ao protocolo, não a qualidade factual
geral nem a segurança do código. A sonda é enviada na conversa aberta e aparece
no histórico; rode-a algumas vezes em cada formato para comparar o comportamento
real do DeepSeek.

## Salvaguardas de acesso

- **Acesso padrão** — restrito à pasta do projeto e com revisão humana. Pastas
  adicionais precisam de grants CRUD/leitura; o acesso amplo pode pedir
  confirmação ou operar automaticamente conforme perfil.
- **Pastas escolhidas** — grants de criar/editar/apagar autorizam a operação sem
  confirmação de escrita adicional; uma nota nova exige **Criar**, enquanto
  **Editar** autoriza somente arquivos existentes. Comandos também executam
  sem confirmação a partir da raiz do projeto, mas os grants não limitam
  os caminhos que um processo pode acessar. O consentimento de leitura continua
  configurável.
- **Consentimento de leitura** — ligado por padrão, inclusive em projetos já
  salvos sem essa configuração. Antes de ler, listar ou buscar no modo Agente,
  o app mostra o escopo e pergunta se pode enviar os dados encontrados ao
  DeepSeek. Em `folders`, mapa, listagem e busca também filtram o conteúdo por
  grants de leitura; uma pasta sem grant não é compartilhada.
- **Relatório de escrita do Agente** — a confirmação retorna somente os planos
  autorizados; o loop aplica cada plano uma vez e só então envia ao DeepSeek o
  resultado real. Aprovações parciais informam quais caminhos ficaram sem
  autorização, evitando relatar falsamente que tudo foi recusado.
- **Caminhos críticos** — operações diretas do app em diretórios protegidos do
  Windows e arquivos na raiz do disco do sistema são recusadas.
- **Limite importante** — o perfil automático não cria um sandbox do Windows.
  Um comando permitido pode chamar outro programa, executar código do projeto
  ou causar efeitos indiretos; use-o somente quando confiar no projeto e nos
  comandos. O modo com confirmação é a escolha mais segura.
- **Sandbox de caminho** — recusa `..`, caminho de rede, ADS
  (`a.txt:oculto`), nome reservado do Windows e symlink/junction nos caminhos
  de arquivo tocados pelo app.
- **Backup antes de tudo** — cada arquivo tocado vira cópia em
  `.deepseek_ui/backups/<data-hora>/`. **Apagar é mover para lá**, nunca `unlink`.
  Nada do que a Kitty faz é irreversível.
- **Diff antes de gravar** — você revê arquivo por arquivo e desmarca o que não
  quiser.
- **Escrita atômica** — grava em temporário e troca. Nunca sobra arquivo pela
  metade.
- **Aviso de truncamento** — se o novo tem menos da metade do tamanho do atual,
  a UI avisa: pode ser resposta cortada por limite de tokens.
- **Comandos em shell livre** — desde 2026-10-19 o agente roda qualquer
  comando no shell do sistema (`cmd.exe` no Windows), começando na raiz do
  projeto: pipes, redirecionamento, `&&`, `;`, `cd` para qualquer pasta e várias
  linhas (viram um script `.cmd` temporário). Sem tempo máximo; **Parar**
  encerra a árvore de processos e o status mostra há quanto tempo o comando
  roda. A saída vai para um arquivo temporário, não um pipe: processo deixado
  em segundo plano (servidor do `adb`, `start /b`) não prende o app. `stdin` fechado, então comando interativo não
  trava. A única proteção é a **confirmação do perfil de Acesso** — nos perfis
  automáticos o comando roda direto, e comando não tem backup nem desfazer.
  Ver `vault/Decisões/ADR-022 Shell livre para o agente.md`.

## Formato legado Markdown/kitty

O metadado vai na **primeira linha dentro do bloco**:

````
```python
# kitty: file=src/calc.py acao=criar
def somar(a, b):
    return a + b
```
````

Também vale o token único na cerca: ```` ```python:src/calc.py:criar ````.

Isso não foi escolhido por gosto — foi medido. Tag XML faz o site cair em modo
HTML cru, onde nenhum bloco é renderizado e **toda quebra de linha vira espaço**.
Por isso não aceitamos XML cru: JSON/XML precisam estar dentro de uma cerca de
código. As sondas antigas e o raciocínio estão em
`vault/Decisões/ADR-002 Formato de resposta.md`; o protocolo novo está em
`vault/Decisões/ADR-011 Protocolo JSON e XML.md`.

## Estrutura

```
main.py            entrada
config.json        URL, seletores e timeouts
configurar_tailscale.bat  configura o Serve (uma vez; pede Administrador)
src/wrapper.py     Selenium: abre o Chrome, lê estado, envia, extrai resposta
src/controller.py  GUI ↔ wrapper + poller que espelha a página
src/bridge.py      thread de fundo → sinal Qt
src/window.py      janela: header, chat, composer; herda RemoteHandlersMixin
src/chat.py        mensagens, Markdown, cards; histórico exposto ao remoto
src/diff_view.py   diálogos de diff e de comando
src/theme.py       cores + QSS
src/sandbox.py     validação de caminho
src/permissions.py perfis de acesso e grants por pasta
src/permission_view.py diálogo de configuração dos perfis
src/backup.py      cópia antes de escrever
src/project.py     raiz, mapa, leitura; histórico de projetos recentes
src/parser.py      resposta Markdown/JSON/XML → ações validadas
src/executor.py    validar, diff, aplicar
src/prompts.py     a skill e as regras de formato
src/agent.py       o loop agêntico (sem Qt)
src/agent_qt.py    o loop numa QThread + confirmação na GUI
src/anexos.py      decide o que vai colado no texto e o que sobe como arquivo
src/session.py     conversa, formato e sondas por projeto
src/remote.py      servidor HTTP loopback + ponte de comandos
src/remote_handlers.py handlers dos comandos remotos (rodam na GUI)
src/remote_panel.html/.css/.js  painel remoto (SPA sem dependências)
src/push.py        chave VAPID, inscrições e Web Push para o celular
src/remote_view.py diálogo do botão Remoto
src/remote_ui.py   helpers sem Qt (achar tailscale, elevar serve)
src/terminal.py    terminal embutido (o seu, sem trava)
src/runner.py      comandos do agente (shell livre, Parar encerra)
vault/             o porquê de cada decisão (Obsidian)
```

Consulte [Estado atual](vault/Estado%20atual.md) e
[Evolução para agente de código](vault/Planos/Evolu%C3%A7%C3%A3o%20para%20agente%20de%20c%C3%B3digo.md)
para evidências e contagens da última regressão completa.

## Testes

Existem **dois estilos** convivendo em `testes/`, e cada um tem o seu runner:

- **Testes pytest** — funções `test_*` e asserções, cobertura de contrato.
  Hoje: 92 testes em 6 arquivos:

  | Arquivo | Casos |
  |---|---|
  | `test_multiplas_instancias.py` | 2 |
  | `test_push.py` | 10 |
  | `test_remote.py` | 17 |
  | `test_remote_handlers.py` | 42 |
  | `test_remote_ponte.py` | 6 |
  | `test_remote_ui.py` | 15 |

  Rodar: `python -m pytest testes/ -q`

- **Scripts standalone** — `X corretos, Y falhas` na saída; cada um roda o
  próprio relatório. Hoje: **608 verificações** em 17 arquivos
  (`test_parser.py`, `test_runner.py`, `test_access_profiles.py`, …).

  Rodar: `python testes/rodar_tudo.py`

Os dois mundos não se cruzam: `testes/conftest.py` faz o pytest ignorar os
scripts standalone, e `testes/rodar_tudo.py` pula os testes pytest. Ao criar
um teste novo, escolha o estilo e adicione o arquivo à lista do lado oposto.
O porquê dessa divisão está em
`vault/Decisões/ADR-014 Dois estilos de teste convivendo.md`.

## Limites que valem saber antes

O DeepSeek web não tem tool-calling nem system prompt. O loop é simulado colando
resultado de volta na conversa, e **cada rodada custa 10–60s**. Não espere a
agilidade do Claude Code: não há tools em paralelo, chamada garantida nem
iteração barata. Por isso o mapa do projeto vai na frente, e por isso existe teto
de rodadas.

## Quando o DeepSeek mudar o layout

Vai mudar — já mudou uma vez durante este projeto. Os seletores estão em
`config.json` e nos scripts JS no topo de `src/wrapper.py`. O que quebra primeiro
e como diagnosticar está em `vault/Referência/Seletores do DeepSeek.md`.

## Tamanho de mensagem e de resposta

O app não corta mais nada por conta própria: mapa, listagem, leitura de arquivo,
busca, saída de comando e conteúdo por rodada vão inteiros. Quem decide o que
cabe é o site, e o app confere os dois sentidos:

- **Ida:** depois do envio, compara o tamanho da mensagem com o que o DeepSeek
  guardou no histórico do servidor. Se chegou menos, para com
  `ErroTamanho` dizendo quantos caracteres foram e quantos ficaram. Se o site
  recusar o envio, o erro traz o tamanho e o aviso que ele mostrou. Antes de
  preencher o campo, as quebras de linha viram LF (o `<textarea>` faz isso
  sozinho); sem isso, saída de comando do Windows (CRLF) dava o falso "o campo
  não aceitou o texto inteiro". Se o campo cortar de verdade, o erro diz
  quantos caracteres entraram de quantos.
- **Volta:** o texto final vem do histórico do servidor (o Markdown cru), não da
  tela. Resposta cortada pelo limite de saída do site, depois dos "Continuar",
  vira `ErroTamanho`; no modo Agente o modelo é avisado para dividir o trabalho.

A barra de status mostra o tamanho da conversa em tokens depois de cada
resposta. Sem a API do histórico (site mudou), o app volta a ler a tela e
decide o fim pela estabilidade do texto (`timeouts.stable_seconds`).

Teste contra o site real, sem passar pela UI:

```
python testes/real_tamanhos_deepseek.py captura coberto
python testes/real_tamanhos_deepseek.py envio 50000 200000
```
