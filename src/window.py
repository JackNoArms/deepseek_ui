"""Janela única: barra de controles no topo, chat no meio, composer embaixo.

Tudo que toca o Selenium roda em QThread — a GUI nunca bloqueia. O retorno vem
por sinal, e o estado dos controles é espelhado pelo poller do Controller via
GuiBridge.

A `MainWindow` herda de `RemoteHandlersMixin`: os métodos `_remote_*` rodam na
thread da GUI quando o servidor HTTP pede (o `RemoteBridge.execute` carrega o
callable e o `MainWindow._executar_tarefa_remota` o executa). Assim as rotas do
painel remoto tocam no `Project`, `WorkspaceStore`, `Executor` e widgets sem
inventar paralelismo.

O sinal `remote_action` avisa o PC quando o celular fez algo (`↗ celular: ...`
no chat, uma linha de status que se apaga em 2,5s). É one-way e não bloqueia o
handler HTTP.

A aba **Habilidades** vive junto com Projeto e Vault. O `SkillsRepo` é amarrado
ao `project.root` em `_set_project`; trocar de projeto troca o repo, a view
recarrega, e o `Agente` recebe o repo como provedor de habilidades no próximo
`rodar`. A view é editável mesmo com agente rodando — mexe só em disco, afeta
o próximo envio.
"""

import codecs
import itertools
import os
import tempfile
import time
from collections import deque
from pathlib import Path

from PyQt6.QtCore import QEventLoop, QUrl, Qt, QThread, QTimer, pyqtSignal
from PyQt6.QtGui import QActionGroup, QDesktopServices, QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QTabWidget,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from src import anexos
from src import processos as proc_bg
from src.agent_qt import AgentWorker
from src.attachment_view import AttachmentPreviewDialog
from src.bridge import GuiBridge
from src.chat import ChatPanel
from src.controller import Controller
from src.diff_view import confirmar_comandos, revisar
from src.executor import Executor, relatorio
from src.parser import parse
from src.permission_view import PermissionDialog
from src.permissions import PermissionPolicy
from src.caminhos import pasta_logs, recurso
from src.queue_view import EditarFilaDialog, QueuePanel
from src.prompts import (
    LEMBRETE,
    SONDA_CAMINHO,
    SONDA_CONTEUDO,
    montar,
    prompt_sonda,
    regras_protocolo,
)
from src.project import (
    Project, auto_conectar, carregar_raiz, salvar_raiz, salvar_tema)
from src.remote import _TOKEN_PADRAO as REMOTE_TOKEN_PATH
from src.remote import RemoteBridge, RemoteServer
from src.remote_handlers import RemoteHandlersMixin
from src.remote_view import RemoteControlDialog
from src.runner import (
    LIMITE_SEM_SAIDA_PADRAO,
    TIMEOUT_PADRAO,
    ComandoRecusado,
    Saida,
    encerrar,
    rodar,
)
from src.sandbox import SandboxError
from src.session import ProjectSession, e_conversa
from src.skills import SkillsRepo
from src.skills_view import SkillsView
from src.terminal import Terminal
from src.theme import (
    TEMAS, TONE, Color, aplicar_tema, soft, stylesheet, tema_atual)
from src.updater_window import UpdaterMixin
from src.vault import (
    WorkspaceStore,
    atualizar_data_nota,
    conteudo_nota,
    garantir_vault,
    nome_arquivo_seguro,
)
from src.vault_view import NewNoteDialog, TextFileDialog


class CallWorker(QThread):
    done = pyqtSignal(object)

    def __init__(self, fn):
        super().__init__()
        self.fn = fn

    def run(self):
        try:
            self.done.emit(self.fn())
        except Exception as e:
            print(f"Erro na tarefa de fundo: {e}")
            self.done.emit(None)


class SendWorker(QThread):
    partial = pyqtSignal(str)
    done = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self, controller, text, arquivos=None):
        super().__init__()
        self.controller = controller
        self.text = text
        self.arquivos = arquivos or []

    def run(self):
        try:
            resp = self.controller.send_message(
                self.text, on_update=self.partial.emit, arquivos=self.arquivos)
        except Exception as e:
            self.failed.emit(str(e))
            return
        self.done.emit(resp or "")


class CommandWorker(QThread):
    """Roda um comando do agente em thread própria, com progresso por sinal.

    `progresso(texto, seg_silencio)` chega a cada pedaço novo de saída; se o
    comando ficar silencioso além de `limite_sem_saida`, é chamado uma vez com
    `texto=""` e `seg_silencio` alto para o card marcar o aviso. O callback do
    `runner` roda nesta thread, então **sempre** passa por sinal antes de tocar
    no Qt da GUI. Nenhuma exceção escapa: `terminou` sempre recebe uma `Saida`,
    com `motivo="erro"` se algo explodir antes do Popen.
    """

    progresso = pyqtSignal(str, float)
    iniciou = pyqtSignal(object)
    terminou = pyqtSignal(object)

    def __init__(self, comando: str, cwd,
                 timeout=TIMEOUT_PADRAO,
                 limite_sem_saida=LIMITE_SEM_SAIDA_PADRAO):
        super().__init__()
        self.comando = comando
        self.cwd = cwd
        self.timeout = timeout
        self.limite_sem_saida = limite_sem_saida

    def run(self):
        try:
            saida = rodar(
                self.comando, self.cwd,
                timeout=self.timeout,
                limite_sem_saida=self.limite_sem_saida,
                ao_iniciar=lambda p: self.iniciou.emit(p),
                ao_progredir=lambda t, s: self.progresso.emit(t, s),
            )
        except ComandoRecusado as e:
            saida = Saida(self.comando, -1, f"(comando recusado)\n{e}",
                          motivo="erro")
        except Exception as e:
            saida = Saida(self.comando, -1, f"(falha inesperada)\n{e}",
                          motivo="erro")
        self.terminou.emit(saida)


class EsperaProntoWorker(QThread):
    """Espera um processo em segundo plano ficar pronto, sem travar a GUI.

    [[ADR-025 Comandos contínuos em segundo plano]]: `esperar_pronto` bloqueia
    nesta thread; a saída chega por sinal e o resultado é `(motivo, posição)`.
    """

    progresso = pyqtSignal(str)
    terminou = pyqtSignal(str, int)

    def __init__(self, gerenciador, processo):
        super().__init__()
        self.gerenciador = gerenciador
        self.processo = processo

    def run(self):
        try:
            motivo, pos = self.gerenciador.esperar_pronto(
                self.processo, ao_progredir=lambda t: self.progresso.emit(t))
        except Exception as e:
            motivo, pos = f"erro: {e}", 0
        self.terminou.emit(motivo, pos)


def _resposta_com_anexos(escolha: str, anexos_resposta) -> tuple[str, list[str]]:
    """Resposta livre + anexos → (texto para o modelo, caminhos para upload).

    Imagem e binário sobem como arquivo; texto pequeno (inline) vai colado no
    fim da resposta, igual ao composer.
    """
    inline, upload = anexos.separar(list(anexos_resposta))
    texto = escolha
    for rotulo, conteudo in inline:
        texto += f"\n\nAnexo `{rotulo}`:\n```\n{conteudo}\n```"
    if upload:
        texto += f"\n\n(Enviei {len(upload)} arquivo(s) junto desta resposta.)"
    return texto, upload


def _separador() -> QFrame:
    """Linha vertical fina entre grupos de botões do cabeçalho."""
    linha = QFrame()
    linha.setObjectName("headerSep")
    linha.setFixedSize(1, 22)
    return linha


class TogglePill(QToolButton):
    """Pílula liga/desliga. `color_on` é um token de `Color` ("ACCENT") ou um hex."""

    def __init__(self, label, color_on, parent=None):
        super().__init__(parent)
        self.label = label
        self._cor = color_on
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._paint(False)

    def set_state(self, on):
        self.setChecked(on)
        self._paint(on)

    @property
    def color_on(self) -> str:
        return (self._cor if self._cor.startswith("#")
                else getattr(Color, self._cor))

    def repintar(self):
        self._paint(self.isChecked())

    def _paint(self, on):
        self.setText(f"{'●' if on else '○'}  {self.label}")
        if on:
            self.setStyleSheet(
                f"QToolButton{{background:{soft(self.color_on)};color:{self.color_on};"
                f"border:1px solid {self.color_on};border-radius:13px;"
                f"padding:5px 13px;font-size:12px;font-weight:700}}"
                f"QToolButton:hover{{background:{Color.SURFACE_HIGH}}}"
                f"QToolButton:disabled{{color:{Color.TEXT_MUTED};"
                f"border-color:{Color.BORDER};background:{Color.SURFACE}}}"
            )
        else:
            self.setStyleSheet(
                f"QToolButton{{background:transparent;color:{Color.TEXT_DIM};"
                f"border:1px solid {Color.BORDER};border-radius:13px;"
                f"padding:5px 13px;font-size:12px;font-weight:600}}"
                f"QToolButton:hover{{color:{Color.TEXT};border-color:{Color.BORDER_STRONG};"
                f"background:{Color.SURFACE_HIGH}}}"
                f"QToolButton:disabled{{color:{Color.TEXT_MUTED};"
                f"border-color:{Color.BORDER_SOFT};background:transparent}}"
            )


def pick_conversation(parent, conversations):
    dlg = QDialog(parent)
    dlg.setWindowTitle("Conversas do DeepSeek")
    dlg.resize(480, 420)
    lay = QVBoxLayout(dlg)
    lay.addWidget(QLabel("Escolha a conversa para abrir:"))
    lst = QListWidget()
    for c in conversations:
        item = QListWidgetItem(c["title"])
        item.setData(Qt.ItemDataRole.UserRole, c["url"])
        lst.addItem(item)
    lst.setCurrentRow(0)
    lst.itemDoubleClicked.connect(lambda _: dlg.accept())
    lay.addWidget(lst, 1)
    buttons = QDialogButtonBox(
        QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
    buttons.accepted.connect(dlg.accept)
    buttons.rejected.connect(dlg.reject)
    lay.addWidget(buttons)
    if dlg.exec() != QDialog.DialogCode.Accepted or not lst.currentItem():
        return None
    return lst.currentItem().data(Qt.ItemDataRole.UserRole)


class Composer(QPlainTextEdit):
    submit = pyqtSignal()
    imagem_colada = pyqtSignal(object)
    arquivos_colados = pyqtSignal(list)

    def keyPressEvent(self, event):
        enter = event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
        shift = event.modifiers() & Qt.KeyboardModifier.ShiftModifier
        if enter and not shift:
            self.submit.emit()
            return
        super().keyPressEvent(event)

    def canInsertFromMimeData(self, source):
        if source.hasImage() or source.hasUrls():
            return True
        return super().canInsertFromMimeData(source)

    def insertFromMimeData(self, source):
        if source.hasImage():
            imagem = source.imageData()
            if imagem is not None:
                self.imagem_colada.emit(imagem)
                return
        if source.hasUrls():
            caminhos = [u.toLocalFile() for u in source.urls() if u.isLocalFile()]
            caminhos = [c for c in caminhos if c]
            if caminhos:
                self.arquivos_colados.emit(caminhos)
                return
        super().insertFromMimeData(source)


class ChipAnexo(QFrame):
    def __init__(self, anexo, on_remove, on_preview=None, parent=None):
        super().__init__(parent)
        self.anexo = anexo
        self.setObjectName("chipAnexo")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 3, 4, 3)
        lay.setSpacing(6)
        rotulo = QToolButton()
        rotulo.setAutoRaise(True)
        rotulo.setObjectName("chipTexto")
        rotulo.setText(f"{anexo.icone} {anexo.rotulo}")
        rotulo.setCursor(Qt.CursorShape.PointingHandCursor)
        rotulo.setToolTip(
            f"{anexo.caminho or anexo.rotulo}\n\n"
            + ("Sobe como arquivo para o DeepSeek."
               if anexo.modo == "upload" else
               "O conteúdo vai colado no texto do pedido."))
        if on_preview:
            rotulo.clicked.connect(lambda: on_preview(anexo))
        lay.addWidget(rotulo)
        fechar = QToolButton()
        fechar.setObjectName("chipFechar")
        fechar.setText("✕")
        fechar.setCursor(Qt.CursorShape.PointingHandCursor)
        fechar.clicked.connect(lambda: on_remove(self))
        lay.addWidget(fechar)


class MainWindow(UpdaterMixin, RemoteHandlersMixin, QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("DeepSeek UI")
        self.resize(1000, 720)
        self.controller = Controller()
        self.bridge = GuiBridge()
        self.controller.set_gui(self.bridge)
        self._workers = []
        self.project = None
        self._precisa_regras = True
        self._vault_instructions = ""
        self._anexos = []
        self._tentou_lembrete = False
        self._formato_envio = "markdown"
        self._sonda_formato = None
        self._formato_em_uso = False
        self._agente = None
        self._skills_repo = None
        self._temporarios_em_voo = []
        self._envio_em_andamento = False
        self._decision_loop = None
        self._comando_em_curso = None
        self._processos = None
        self._acompanhamentos = {}
        self._parar_comandos = False
        self._tree_scan_generation = {"projeto": 0, "vault": 0}
        self._tree_fill_generation = {"projeto": 0, "vault": 0}
        self._fila_mensagens = deque()
        self._ids_pedido = itertools.count(1)
        self._anexos_decisao_remota = {}

        self._decisoes_remotas = {}
        self.remote_bridge = RemoteBridge()
        self.remote = None
        try:
            self.remote = RemoteServer(bridge=self.remote_bridge)
            self.remote.start()
            self.remote_bridge.decision_answered.connect(self._decisao_remota)
            self.remote_bridge.execute.connect(self._executar_tarefa_remota)
            self.remote_bridge.remote_action.connect(self._acao_remota)
            self.remote.set_handlers(self)
            self.remote.update(theme=tema_atual())
        except Exception as e:
            print(f"Painel remoto indisponível: {type(e).__name__} - {e}")
            self.remote = None

        root = QWidget()
        root.setObjectName("root")
        lay = QVBoxLayout(root)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(self._build_header())
        self.chat = ChatPanel()
        self.terminal = Terminal()
        self.terminal.fechado.connect(lambda: self._mostrar_terminal(False))
        self.terminal.hide()
        self.divisor = QSplitter(Qt.Orientation.Vertical)
        self.divisor.addWidget(self.chat)
        self.divisor.addWidget(self.terminal)
        self.divisor.setStretchFactor(0, 3)
        self.divisor.setStretchFactor(1, 1)
        self.workspace_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.workspace_splitter.addWidget(self._build_workspace_panel())
        self.workspace_splitter.addWidget(self.divisor)
        self.workspace_splitter.setStretchFactor(0, 0)
        self.workspace_splitter.setStretchFactor(1, 1)
        self.workspace_splitter.setSizes([270, 730])
        lay.addWidget(self.workspace_splitter, 1)
        lay.addWidget(self._build_composer())
        self.setCentralWidget(root)
        self._wire_bridge()
        atalho = QShortcut(QKeySequence("Ctrl+`"), self)
        atalho.activated.connect(
            lambda: self._mostrar_terminal(not self.terminal.isVisible()))
        self._on_controls(False)
        self._atualizar_arvore()
        self._carregar_instrucoes_vault()
        self._atualizar_feedback_acesso()
        ultima = carregar_raiz()
        if ultima:
            self._set_project(ultima, avisar=False)
        if (auto_conectar() and self.project
                and ProjectSession(self.project.root).url()):
            QTimer.singleShot(300, self._auto_conectar)

    def _auto_conectar(self):
        self._on_status(f"Retomando {self.project.nome} — abrindo o navegador…", "muted")
        self.btn_conn.setEnabled(False)
        def done(_):
            self.btn_conn.setEnabled(True)
            if self.controller.is_connected:
                self._retomar_conversa()
        self._bg(self.controller.connect, done)

    def _build_workspace_panel(self):
        self.workspace_tabs = QTabWidget()
        self.workspace_tabs.setObjectName("workspaceTabs")
        self.workspace_tabs.setMinimumWidth(210)
        projeto = QWidget()
        projeto.setObjectName("workspacePage")
        projeto_lay = QVBoxLayout(projeto)
        projeto_lay.setContentsMargins(8, 8, 8, 8)
        projeto_lay.setSpacing(6)
        self.lbl_tree_project = QLabel("Nenhum projeto aberto")
        self.lbl_tree_project.setWordWrap(True)
        projeto_lay.addWidget(self.lbl_tree_project)
        self.project_tree = QTreeWidget()
        self.project_tree.setObjectName("projectTree")
        self.project_tree.setHeaderLabel("Arquivos")
        self.project_tree.setToolTip("Arquivos de texto visíveis no projeto aberto")
        projeto_lay.addWidget(self.project_tree, 1)
        self.btn_project_folder = QPushButton("Nova pasta")
        self.btn_project_file = QPushButton("Novo arquivo")
        self.btn_project_refresh = QPushButton("Atualizar")
        self.btn_project_folder.clicked.connect(
            lambda: self._criar_pasta_workspace("projeto"))
        self.btn_project_file.clicked.connect(
            lambda: self._criar_arquivo_workspace("projeto"))
        self.btn_project_refresh.clicked.connect(self._atualizar_arvore)
        projeto_botoes = QHBoxLayout()
        for botao in (self.btn_project_folder, self.btn_project_file,
                      self.btn_project_refresh):
            projeto_botoes.addWidget(botao)
        projeto_lay.addLayout(projeto_botoes)
        self.project_tree.setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu)
        self.project_tree.customContextMenuRequested.connect(
            lambda pos: self._menu_workspace("projeto", pos))
        self.project_tree.itemDoubleClicked.connect(
            lambda item, _col: self._abrir_item_workspace("projeto", item))
        self.workspace_tabs.addTab(projeto, "Projeto")
        vault = QWidget()
        vault.setObjectName("workspacePage")
        vault_lay = QVBoxLayout(vault)
        vault_lay.setContentsMargins(8, 8, 8, 8)
        vault_lay.setSpacing(6)
        self.lbl_vault_path = QLabel("Nenhum vault vinculado")
        self.lbl_vault_path.setWordWrap(True)
        vault_lay.addWidget(self.lbl_vault_path)
        self.vault_tree = QTreeWidget()
        self.vault_tree.setObjectName("vaultTree")
        self.vault_tree.setHeaderLabel("Notas e pastas")
        self.vault_tree.setToolTip(
            "Duplo clique edita arquivos; botão direito abre as ações CRUD.")
        vault_lay.addWidget(self.vault_tree, 1)
        self.btn_vault_note = QPushButton("Nova nota")
        self.btn_vault_folder = QPushButton("Nova pasta")
        self.btn_vault_refresh = QPushButton("Atualizar")
        self.btn_vault_note.clicked.connect(self._criar_nota_vault)
        self.btn_vault_folder.clicked.connect(
            lambda: self._criar_pasta_workspace("vault"))
        self.btn_vault_refresh.clicked.connect(self._atualizar_arvore_vault)
        vault_botoes = QHBoxLayout()
        for botao in (self.btn_vault_note, self.btn_vault_folder,
                      self.btn_vault_refresh):
            vault_botoes.addWidget(botao)
        vault_lay.addLayout(vault_botoes)
        self.btn_vault_explorer = QPushButton("Abrir pasta do vault")
        self.btn_vault_explorer.clicked.connect(self._abrir_vault_no_explorer)
        vault_lay.addWidget(self.btn_vault_explorer)
        self.vault_tree.setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu)
        self.vault_tree.customContextMenuRequested.connect(
            lambda pos: self._menu_workspace("vault", pos))
        self.vault_tree.itemDoubleClicked.connect(
            lambda item, _col: self._abrir_item_workspace("vault", item))
        self.workspace_tabs.addTab(vault, "Vault")

        self.skills_view = SkillsView(None)
        self.workspace_tabs.addTab(self.skills_view, "Habilidades")

        return self.workspace_tabs

    def _build_header(self):
        header = QFrame()
        header.setObjectName("header")
        lay = QHBoxLayout(header)
        lay.setContentsMargins(14, 10, 14, 10)
        lay.setSpacing(10)
        marca = QLabel("◆")
        marca.setObjectName("brandMark")
        lay.addWidget(marca)
        title_box = QVBoxLayout()
        title_box.setSpacing(0)
        brand = QLabel("DeepSeek UI")
        brand.setObjectName("brand")
        self.lbl_status = QLabel("Desconectado")
        self.lbl_status.setObjectName("status")
        self.lbl_status.setMinimumWidth(0)
        self.lbl_status.setMaximumWidth(360)
        self.lbl_status.setSizePolicy(QSizePolicy.Policy.Ignored,
                                      QSizePolicy.Policy.Preferred)
        title_box.addWidget(brand)
        title_box.addWidget(self.lbl_status)
        lay.addLayout(title_box)
        lay.addSpacing(14)
        self.pill_deepthink = TogglePill("DeepThink", "DEEPTHINK")
        self.pill_deepthink.clicked.connect(
            lambda: self._bg(self.controller.toggle_deepthink))
        lay.addWidget(self.pill_deepthink)
        self.pill_search = TogglePill("Search", "SEARCH")
        self.pill_search.clicked.connect(lambda: self._bg(self.controller.toggle_search))
        lay.addWidget(self.pill_search)
        lay.addStretch(1)
        self.lbl_project = QLabel("nenhuma pasta aberta")
        self.lbl_project.setObjectName("project")
        self.lbl_project.setToolTip("Nenhuma pasta autorizada: a Kitty não pode tocar em arquivo.")
        lay.addWidget(self.lbl_project)
        lay.addWidget(_separador())
        self.btn_folder = QPushButton("Abrir pasta")
        self.btn_folder.setObjectName("openFolder")
        self.btn_folder.clicked.connect(self._open_folder)
        lay.addWidget(self.btn_folder)
        self.btn_vault = QPushButton("Abrir vault")
        self.btn_vault.setObjectName("openFolder")
        self.btn_vault.setToolTip("Escolhe e vincula o vault deste projeto")
        self.btn_vault.clicked.connect(self._open_vault)
        lay.addWidget(self.btn_vault)
        self.btn_permissions = QPushButton("Acesso")
        self.btn_permissions.setObjectName("openFolder")
        self.btn_permissions.setToolTip(
            "Configura o escopo, grants por pasta e confirmação de leitura "
            "antes de compartilhar dados com o DeepSeek")
        self.btn_permissions.clicked.connect(self._configurar_permissoes)
        lay.addWidget(self.btn_permissions)
        self.btn_remote = QPushButton("Remoto")
        self.btn_remote.setObjectName("openFolder")
        self.btn_remote.setToolTip(
            "Painel no celular via Tailscale. Mostra o link, copia, e "
            "oferece ativar/reiniciar o serve (pede Administrador).")
        self.btn_remote.clicked.connect(self._abrir_controle_remoto)
        lay.addWidget(self.btn_remote)
        lay.addWidget(_separador())
        self.chk_agente = TogglePill("Agente", "ACCENT")
        self.chk_agente.set_state(True)
        self.chk_agente.setToolTip(
            "Ligado: a Kitty lê arquivos e trabalha em várias rodadas até terminar.\n"
            "Desligado: uma pergunta, uma resposta.")
        self.chk_agente.clicked.connect(
            lambda: self.chk_agente.set_state(self.chk_agente.isChecked()))
        lay.addWidget(self.chk_agente)
        self.btn_attach = QPushButton("Anexar")
        self.btn_attach.setObjectName("openFolder")
        self.btn_attach.setToolTip("Colar arquivos do projeto no próximo pedido")
        self.btn_attach.clicked.connect(self._anexar)
        lay.addWidget(self.btn_attach)
        self.btn_explorer = QPushButton("Explorer")
        self.btn_explorer.setObjectName("openFolder")
        self.btn_explorer.setToolTip("Abre a pasta do projeto no Explorer")
        self.btn_explorer.clicked.connect(self._abrir_no_explorer)
        lay.addWidget(self.btn_explorer)
        self.btn_terminal = QPushButton("Terminal")
        self.btn_terminal.setObjectName("openFolder")
        self.btn_terminal.setCheckable(True)
        self.btn_terminal.setToolTip("Mostra ou esconde o terminal (Ctrl+`)")
        self.btn_terminal.clicked.connect(
            lambda: self._mostrar_terminal(self.btn_terminal.isChecked()))
        lay.addWidget(self.btn_terminal)
        self.btn_processos = QPushButton("Processos")
        self.btn_processos.setObjectName("openFolder")
        self.btn_processos.setToolTip(
            "Comandos que seguem rodando em segundo plano (servidor de dev, watch): "
            "ver log ou parar")
        menu_processos = QMenu(self.btn_processos)
        menu_processos.aboutToShow.connect(self._montar_menu_processos)
        self.btn_processos.setMenu(menu_processos)
        lay.addWidget(self.btn_processos)
        lay.addWidget(_separador())
        self.btn_tema = QPushButton("Tema")
        self.btn_tema.setObjectName("openFolder")
        self.btn_tema.setToolTip("Troca o tema do app (o celular acompanha)")
        menu_tema = QMenu(self.btn_tema)
        self._grupo_tema = QActionGroup(menu_tema)
        self._grupo_tema.setExclusive(True)
        for nome, tema in TEMAS.items():
            acao = menu_tema.addAction(tema["rotulo"])
            acao.setCheckable(True)
            acao.setChecked(nome == tema_atual())
            acao.setData(nome)
            self._grupo_tema.addAction(acao)
            acao.triggered.connect(
                lambda _marcado=False, n=nome: self._trocar_tema(n))
        self.btn_tema.setMenu(menu_tema)
        lay.addWidget(self.btn_tema)
        lay.addWidget(_separador())
        self.btn_new = QPushButton("Nova conversa")
        self.btn_new.setToolTip(
            "Inicia uma conversa nova no DeepSeek (atalho Ctrl+J)")
        self.btn_new.clicked.connect(self._new_chat)
        lay.addWidget(self.btn_new)
        self.btn_history = QPushButton("Conversas")
        self.btn_history.clicked.connect(self._open_history)
        lay.addWidget(self.btn_history)
        lay.addWidget(_separador())
        self.btn_conn = QPushButton("Conectar")
        self.btn_conn.setObjectName("connect")
        self.btn_conn.clicked.connect(self._toggle_connection)
        lay.addWidget(self.btn_conn)
        return header

    def _build_composer(self):
        frame = QFrame()
        frame.setObjectName("composer")
        fora = QVBoxLayout(frame)
        fora.setContentsMargins(14, 8, 14, 12)
        fora.setSpacing(8)
        self.painel_fila = QueuePanel()
        self.painel_fila.cancelar.connect(self._cancelar_da_fila)
        self.painel_fila.editar.connect(self._editar_item_fila)
        self.painel_fila.limpar.connect(self._limpar_fila)
        fora.addWidget(self.painel_fila)
        self.barra_anexos = QFrame()
        self.barra_anexos.setObjectName("barraAnexos")
        self.lay_anexos = QHBoxLayout(self.barra_anexos)
        self.lay_anexos.setContentsMargins(0, 0, 0, 0)
        self.lay_anexos.setSpacing(6)
        self.lay_anexos.addStretch(1)
        self.barra_anexos.hide()
        fora.addWidget(self.barra_anexos)
        linha_formato = QHBoxLayout()
        linha_formato.setSpacing(6)
        linha_formato.addWidget(QLabel("Retorno:"))
        self.cmb_formato = QComboBox()
        self.cmb_formato.setObjectName("responseFormat")
        self.cmb_formato.view().setObjectName("responseFormatOptions")
        self.cmb_formato.addItem("Markdown (legado)", "markdown")
        self.cmb_formato.addItem("JSON", "json")
        self.cmb_formato.addItem("XML", "xml")
        self.cmb_formato.setToolTip(
            "Formato salvo para este projeto. Pode ser alterado sem conexão; "
            "a sonda e o envio exigem conexão com o DeepSeek.")
        self.cmb_formato.currentIndexChanged.connect(self._formato_alterado)
        linha_formato.addWidget(self.cmb_formato)
        self.btn_probe = QPushButton("Testar formato")
        self.btn_probe.setToolTip(
            "Envia uma ação de teste ao DeepSeek. A resposta é validada, "
            "mas a ação nunca é executada.")
        self.btn_probe.clicked.connect(self._sondar_formato)
        linha_formato.addWidget(self.btn_probe)
        self.lbl_sondas = QLabel("Sondas válidas — JSON: 0/0 · XML: 0/0")
        self.lbl_sondas.setToolTip(
            "Contagem por projeto de respostas de sonda que respeitaram "
            "o formato e o conteúdo esperado. É uma medida de aderência ao "
            "protocolo, não uma avaliação da qualidade factual do modelo.")
        linha_formato.addWidget(self.lbl_sondas)
        self.lbl_access_summary = QLabel()
        self.lbl_access_summary.setObjectName("accessSummary")
        linha_formato.addWidget(self.lbl_access_summary)
        self.lbl_queue = QLabel()
        self.lbl_queue.setObjectName("queueStatus")
        linha_formato.addWidget(self.lbl_queue)
        linha_formato.addStretch(1)
        fora.addLayout(linha_formato)
        lay = QHBoxLayout()
        lay.setSpacing(10)
        fora.addLayout(lay)
        self.input = Composer()
        self.input.setObjectName("input")
        self.input.setPlaceholderText(
            "Pergunte ao DeepSeek…   Enter envia · Shift+Enter quebra linha · "
            "Ctrl+V cola imagem ou arquivo")
        self.input.setFixedHeight(76)
        self.input.submit.connect(self._send)
        self.input.imagem_colada.connect(self._colar_imagem)
        self.input.arquivos_colados.connect(self._colar_arquivos)
        lay.addWidget(self.input, 1)
        coluna = QVBoxLayout()
        coluna.setSpacing(6)
        self.btn_stop = QPushButton("Parar")
        self.btn_stop.setObjectName("connectOn")
        self.btn_stop.clicked.connect(self._parar_agente)
        self.btn_stop.hide()
        coluna.addWidget(self.btn_stop)
        self.btn_send = QPushButton("Enviar")
        self.btn_send.setObjectName("send")
        self.btn_send.clicked.connect(self._send)
        coluna.addWidget(self.btn_send)
        lay.addLayout(coluna)
        return frame

    def _wire_bridge(self):
        b = self.bridge
        b.status.connect(self._on_status)
        b.controls_enabled.connect(self._on_controls)
        b.deepthink.connect(self.pill_deepthink.set_state)
        b.search.connect(self.pill_search.set_state)
        b.search_available.connect(self._on_search_available)

    def _bg(self, fn, on_done=None):
        worker = CallWorker(fn)
        if on_done:
            worker.done.connect(on_done)
        self._start(worker)

    def _start(self, worker):
        self._workers.append(worker)
        worker.finished.connect(lambda: self._workers.remove(worker)
                                if worker in self._workers else None)
        worker.start()

    def _publicar_estado_remoto(self):
        if not self.remote:
            return
        self.remote.update(
            project=(self.project.nome if self.project else None),
            connected=bool(self.controller.is_connected),
            agent_active=self._agente is not None,
            queue=len(self._fila_mensagens),
            queue_items=self._itens_fila(),
        )

    def _decisao_remota(self, id_card: str, escolha: str):
        anexos_resposta = self._anexos_decisao_remota.pop(id_card, [])
        registrar = self._decisoes_remotas.get(id_card)
        if registrar is None:
            for anexo in anexos_resposta:
                anexo.descartar()
            return
        registrar(escolha, origem="celular", anexos_resposta=anexos_resposta)

    def _itens_fila(self) -> list[dict]:
        return [
            {"id": pedido[4], "texto": pedido[0],
             "anexos": [a.rotulo for a in pedido[3]], "agente": bool(pedido[2])}
            for pedido in self._fila_mensagens
        ]

    def _fila_mudou(self):
        if hasattr(self, "painel_fila"):
            self.painel_fila.set_itens(self._itens_fila())
        self._atualizar_feedback_acesso()
        self._atualizar_controles_ocupado()
        self._atualizar_estado_formato()
        self._publicar_estado_remoto()

    def _cancelar_da_fila(self, id_pedido: str) -> bool:
        for pedido in list(self._fila_mensagens):
            if pedido[4] == id_pedido:
                self._fila_mensagens.remove(pedido)
                for anexo in pedido[3]:
                    anexo.descartar()
                resumo = " ".join(pedido[0].split())
                if len(resumo) > 60:
                    resumo = resumo[:59] + "…"
                self._on_status(f"Removida da fila: {resumo}", "muted")
                self._fila_mudou()
                return True
        return False

    def _editar_texto_fila(self, id_pedido: str, texto: str) -> bool:
        texto = (texto or "").strip()
        if not texto:
            return False
        for i, pedido in enumerate(self._fila_mensagens):
            if pedido[4] == id_pedido:
                self._fila_mensagens[i] = (texto,) + tuple(pedido[1:])
                self._fila_mudou()
                return True
        return False

    def _editar_item_fila(self, id_pedido: str):
        atual = next((p for p in self._fila_mensagens if p[4] == id_pedido), None)
        if atual is None:
            return
        dialogo = EditarFilaDialog(atual[0], self)
        if dialogo.exec() != QDialog.DialogCode.Accepted:
            return
        if not dialogo.texto():
            self._on_status("Texto vazio — para tirar da fila use ✕", "danger")
        elif self._editar_texto_fila(id_pedido, dialogo.texto()):
            self._on_status("Mensagem da fila editada", "success")
        else:
            self._on_status("A mensagem já saiu da fila; nada foi alterado", "danger")

    def _limpar_fila(self) -> int:
        total = len(self._fila_mensagens)
        for pedido in self._fila_mensagens:
            for anexo in pedido[3]:
                anexo.descartar()
        self._fila_mensagens.clear()
        if total:
            self._on_status(f"Fila limpa: {total} mensagem(ns) cancelada(s)", "muted")
        self._fila_mudou()
        return total

    def _executar_tarefa_remota(self, tarefa):
        try:
            tarefa()
        except Exception as e:
            print(f"Falha em tarefa remota: {type(e).__name__} - {e}")

    def _acao_remota(self, metodo: str, resumo: str):
        try:
            self.chat.add_system(f"↗ celular: {resumo}")
        except Exception:
            return
        texto = f"↗ {resumo}"
        self.lbl_status.setText(texto)

        def restaurar():
            if self.lbl_status.text() == texto:
                self.lbl_status.setText("Pronto")

        QTimer.singleShot(2500, restaurar)

    def _adicionar_chip_anexo(self, anexo):
        chip = ChipAnexo(anexo, self._remover_anexo, self._previsualizar_anexo)
        self.lay_anexos.insertWidget(self.lay_anexos.count() - 1, chip)
        self.barra_anexos.show()

    def _abrir_controle_remoto(self):
        bat = recurso("configurar_tailscale.bat")
        porta = self.remote.porta if self.remote else 8765
        if self.remote is None:
            self.chat.add_system(
                "O painel HTTP local não subiu (porta ocupada?). O diálogo "
                "ainda configura o Tailscale; só não terá o painel para "
                "servir.")
        dialogo = RemoteControlDialog(
            self, porta=porta, token_path=REMOTE_TOKEN_PATH, bat_path=bat)
        dialogo.exec()

    def _trocar_tema(self, nome: str):
        nome = aplicar_tema(nome)
        app = QApplication.instance()
        if app is not None:
            app.setStyleSheet(stylesheet())
        for pill in (self.pill_deepthink, self.pill_search, self.chk_agente):
            pill.repintar()
        self._on_status(self.lbl_status.text(), getattr(self, "_tom_status", "muted"))
        for acao in self._grupo_tema.actions():
            acao.setChecked(acao.data() == nome)
        salvar_tema(nome)
        if self.remote:
            self.remote.update(theme=nome)

    def _on_status(self, msg, tone):
        self._tom_status = tone
        self.lbl_status.setText(msg)
        self.lbl_status.setStyleSheet(f"font-size:11px;color:{TONE.get(tone, Color.TEXT_DIM)}")
        if self.remote:
            self.remote.update(status=msg, status_tone=tone)
            self._publicar_estado_remoto()

    def _on_controls(self, enabled):
        for w in (self.pill_deepthink, self.btn_new, self.btn_attach, self.chk_agente,
                  self.btn_history, self.input, self.btn_send, self.btn_probe):
            w.setEnabled(enabled)
        self._atualizar_estado_formato()
        self.pill_search.setEnabled(enabled and self.controller.search_available)
        self.btn_conn.setText("Desconectar" if enabled else "Conectar")
        self.btn_conn.setObjectName("connectOn" if enabled else "connect")
        self.btn_conn.style().unpolish(self.btn_conn)
        self.btn_conn.style().polish(self.btn_conn)
        self._atualizar_controles_ocupado()

    def _on_search_available(self, available):
        self.pill_search.setEnabled(available and self.controller.is_connected)

    def _formato_atual(self) -> str:
        return self.cmb_formato.currentData() or "markdown"

    def _formato_alterado(self, _indice):
        if self.project:
            sessao = ProjectSession(self.project.root)
            if not sessao.salvar_formato_resposta(self._formato_atual()):
                self._on_status("Não consegui salvar o formato deste projeto", "danger")
                self._carregar_formato_projeto()
                return
        self._atualizar_sondas()

    def _carregar_formato_projeto(self):
        formato = (ProjectSession(self.project.root).formato_resposta()
                   if self.project else "markdown")
        bloqueado = self.cmb_formato.blockSignals(True)
        self.cmb_formato.setCurrentIndex(max(0, self.cmb_formato.findData(formato)))
        self.cmb_formato.blockSignals(bloqueado)
        self._atualizar_sondas()
        self._atualizar_estado_formato()

    def _atualizar_estado_formato(self):
        projeto_disponivel = (
            self.project is not None and not self._formato_em_uso
            and not self._envio_em_andamento and self._agente is None
            and not self._fila_mensagens)
        self.cmb_formato.setEnabled(projeto_disponivel)
        self.btn_probe.setEnabled(
            projeto_disponivel and self.controller.is_connected)

    def _atualizar_sondas(self):
        sondas = (ProjectSession(self.project.root).sondas_formato()
                  if self.project else {
                      "json": {"tests": 0, "valid": 0},
                      "xml": {"tests": 0, "valid": 0},
                  })
        json_stats, xml_stats = sondas["json"], sondas["xml"]
        self.lbl_sondas.setText(
            f"Sondas válidas — JSON: {json_stats['valid']}/{json_stats['tests']} "
            f"· XML: {xml_stats['valid']}/{xml_stats['tests']}")

    def _sondar_formato(self):
        if not self.controller.is_connected:
            self._on_status("Conecte o navegador antes de testar o formato", "danger")
            return
        if self._agente is not None or not self.btn_send.isEnabled():
            self._on_status("Aguarde o envio atual terminar antes da sonda", "danger")
            return
        formato = self._formato_atual()
        if formato not in ("json", "xml"):
            self._on_status("Selecione JSON ou XML para testar o formato", "danger")
            return
        self._tentou_lembrete = False
        self._sonda_formato = formato
        self._formato_envio = formato
        pedido = prompt_sonda(formato)
        self.chat.add_user(pedido)
        self._enviar_bruto(pedido)
        self._on_status(f"Testando resposta {formato.upper()}…", "muted")

    def _registrar_resultado_sonda(self, resposta: str, formato: str):
        lido = parse(resposta or "", formato=formato)
        valida = (
            lido.valida
            and bool(lido.resumo.strip())
            and len(lido.acoes) == 1
            and lido.acoes[0].verbo == "criar"
            and lido.acoes[0].caminho == SONDA_CAMINHO
            and lido.acoes[0].conteudo == SONDA_CONTEUDO
        )
        mensagem = (f"Sonda {formato.upper()}: "
                    + ("válida; a ação de teste não foi executada."
                       if valida else
                       "inválida; o formato ou o conteúdo não correspondeu."))
        if not lido.valida:
            mensagem += f" Motivo: {lido.erro}"
        elif not valida:
            mensagem += " Esperava uma ação create com o caminho e conteúdo de teste."
        if self.project:
            salva = ProjectSession(self.project.root).registrar_sonda_formato(
                formato, bool(valida))
            if not salva:
                mensagem += " Não foi possível salvar a contagem no projeto."
        else:
            mensagem += " Abra um projeto para persistir a contagem."
        self.chat.add_system(mensagem)
        self._atualizar_sondas()
        self._on_status(
            f"Sonda {formato.upper()} {'válida' if valida else 'inválida'}",
            "success" if valida else "danger")

    def _toggle_connection(self):
        self.btn_conn.setEnabled(False)
        connected = self.controller.is_connected
        self._on_status("Desconectando…" if connected else "Abrindo o navegador…", "muted")
        def done(_):
            self.btn_conn.setEnabled(True)
            if self.controller.is_connected:
                self._retomar_conversa()
        self._bg(self.controller.disconnect if connected else self.controller.connect, done)

    def _mostrar_terminal(self, mostrar: bool):
        self.btn_terminal.setChecked(mostrar)
        self.terminal.setVisible(mostrar)
        if mostrar:
            if self.project:
                self.terminal.definir_cwd(self.project.root)
            altura = self.divisor.height() or 600
            self.divisor.setSizes([int(altura * 0.66), int(altura * 0.34)])
            self.terminal.entrada.setFocus()

    def _abrir_no_explorer(self):
        if not self.project:
            self._on_status("Abra uma pasta primeiro", "danger")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.project.root)))

    def _retomar_conversa(self):
        if not (self.project and self.controller.is_connected):
            return
        url = ProjectSession(self.project.root).url()
        if not url:
            return
        self._on_status(f"Retomando a conversa de {self.project.nome}…", "muted")
        def carregar():
            if self.controller.open_conversation(url):
                return self.controller.extract_history()
            return None
        self._bg(carregar, self._conversa_retomada)

    def _conversa_retomada(self, mensagens):
        if mensagens is None:
            self._on_status("Não consegui reabrir a conversa salva", "danger")
            return
        self.chat.load_history(
            mensagens, formato=self._formato_atual(),
            on_decision=self._enviar_decisao)
        self._precisa_regras = not ProjectSession(self.project.root).regras_enviadas()
        self._on_status(
            f"Conversa de {self.project.nome} retomada — {len(mensagens)} mensagens",
            "success")

    def _guardar_conversa(self):
        if not (self.project and self.controller.is_connected):
            return
        try:
            url = self.controller.current_url()
        except Exception:
            return
        if e_conversa(url):
            ProjectSession(self.project.root).salvar_url(
                url, regras_enviadas=not self._precisa_regras)

    def _new_chat(self):
        if self._envio_em_andamento or self._agente is not None or self._fila_mensagens:
            self._on_status(
                "Aguarde o envio e a fila terminarem antes de criar outra conversa",
                "danger")
            return
        self._on_status("Abrindo conversa nova…", "muted")
        def done(ok):
            if not ok:
                self._on_status("Não consegui criar uma conversa nova no DeepSeek",
                                "danger")
                return
            self.chat.clear()
            self._precisa_regras = True
            self._limpar_anexos()
            if self.project:
                ProjectSession(self.project.root).esquecer()
            self._on_status("Conversa nova", "success")
        self._bg(self.controller.new_chat, done)

    def _open_history(self):
        self._on_status("Lendo a lista de conversas…", "muted")
        self._bg(self.controller.list_conversations, self._on_conversations)

    def _on_conversations(self, conversations):
        if not conversations:
            self._on_status("Nenhuma conversa na barra lateral", "danger")
            return
        url = pick_conversation(self, conversations)
        if not url:
            self._on_status("Pronto", "muted")
            return
        self._on_status("Abrindo a conversa…", "muted")
        def load():
            if self.controller.open_conversation(url):
                return self.controller.extract_history()
            return []
        self._bg(load, self._on_history_loaded)

    def _on_history_loaded(self, messages):
        self.chat.load_history(
            messages or [], formato=self._formato_atual(),
            on_decision=self._enviar_decisao)
        self._guardar_conversa()
        self._on_status(f"{len(messages or [])} mensagens carregadas", "success")

    def _send(self):
        text = self.input.toPlainText().strip()
        if not text and not self._anexos:
            return
        if not text:
            text = "Analise os anexos enviados e resuma o conteúdo relevante."
        if not self.controller.is_connected:
            self._on_status("Conecte o navegador primeiro", "danger")
            return
        agente = self.chk_agente.isChecked()
        if agente and not self.project:
            self._on_status("O modo Agente precisa de uma pasta aberta", "danger")
            return
        self.input.clear()
        pendentes = list(self._anexos)
        self._limpar_anexos(descartar=False)
        self._enfileirar_ou_iniciar(text, agente, pendentes)

    def _ocupado(self) -> bool:
        return bool(self._envio_em_andamento or self._agente is not None
                    or self._fila_mensagens)

    def _enfileirar_ou_iniciar(self, text, agente, pendentes):
        pedido = (text, self._formato_atual(), agente, pendentes,
                  f"q{next(self._ids_pedido)}")
        if self._ocupado():
            self._fila_mensagens.append(pedido)
            self._on_status(
                f"Na fila: posição {len(self._fila_mensagens)}", "accent")
            self._fila_mudou()
            return
        self.chat.add_user(text)
        self._iniciar_pedido(pedido)

    def _iniciar_pedido(self, pedido):
        texto, formato, agente, pendentes = pedido[:4]
        self._sonda_formato = None
        self._formato_envio = formato
        self._temporarios_em_voo = pendentes
        incluir_mapa = self._autorizar_compartilhamento_estrutura()
        if pendentes:
            self.chat.add_system(
                "Anexado: " + ", ".join(f"{a.icone} {a.rotulo}" for a in pendentes))
        if agente:
            inline, upload = anexos.separar(pendentes)
            self._rodar_agente(
                texto, incluir_mapa=incluir_mapa,
                anexos_inline=inline, arquivos=upload)
            return
        inline, upload = anexos.separar(pendentes)
        mensagem = montar(
            texto, project=self.project, primeira=self._precisa_regras,
            anexos=inline, instrucoes=self._vault_instructions,
            formato=formato, incluir_mapa=incluir_mapa,
            habilidades=(self._skills_repo.all() if self._skills_repo else None))
        self._precisa_regras = False
        self._tentou_lembrete = False
        self._enviar_bruto(mensagem, arquivos=upload)

    def _enviar_bruto(self, mensagem: str, arquivos=None):
        self._formato_em_uso = True
        self._envio_em_andamento = True
        self.chat.start_agent()
        self._atualizar_estado_formato()
        self._atualizar_controles_ocupado()
        worker = SendWorker(self.controller, mensagem, arquivos)
        worker.partial.connect(self._atualizar_resposta_parcial)
        worker.done.connect(self._on_response)
        worker.failed.connect(self._on_send_error)
        self._start(worker)

    def _anexar(self):
        inicial = str(self.project.root) if self.project else ""
        caminhos, _ = QFileDialog.getOpenFileNames(self, "Anexar arquivos", inicial)
        if caminhos:
            self._colar_arquivos(caminhos)

    def _colar_imagem(self, imagem):
        anexo = anexos.de_imagem(imagem)
        if not anexo:
            self._on_status("Não consegui ler a imagem da área de transferência", "danger")
            return
        self._add_anexo(anexo)
        self._on_status(f"Anexado: {anexo.rotulo}", "success")

    def _colar_arquivos(self, caminhos):
        raiz = self.project.root if self.project else None
        novos, ignorados = [], []
        for caminho in caminhos:
            anexo = anexos.de_arquivo(caminho, raiz)
            if anexo:
                self._add_anexo(anexo)
                novos.append(anexo.rotulo)
            else:
                ignorados.append(os.path.basename(caminho))
        if novos:
            self._on_status(f"Anexado: {', '.join(novos)}", "success")
        if ignorados:
            self._on_status(f"Não anexei (não é arquivo): {', '.join(ignorados)}", "danger")

    def _add_anexo(self, anexo):
        self._anexos.append(anexo)
        self._adicionar_chip_anexo(anexo)

    def _previsualizar_anexo(self, anexo):
        AttachmentPreviewDialog(anexo, self).exec()

    def _remover_anexo(self, chip):
        if chip.anexo in self._anexos:
            self._anexos.remove(chip.anexo)
        chip.anexo.descartar()
        chip.setParent(None)
        chip.deleteLater()
        if not self._anexos:
            self.barra_anexos.hide()

    def _limpar_anexos(self, descartar=True):
        for i in reversed(range(self.lay_anexos.count())):
            w = self.lay_anexos.itemAt(i).widget()
            if isinstance(w, ChipAnexo):
                w.setParent(None)
                w.deleteLater()
        if descartar:
            for a in self._anexos:
                a.descartar()
        self._anexos = []
        self.barra_anexos.hide()

    def _on_response(self, response):
        for a in self._temporarios_em_voo:
            a.descartar()
        self._temporarios_em_voo = []
        resposta_lida = parse(response or "", formato=self._formato_envio)
        self.chat.finish_agent(
            response, resposta_lida, formato=self._formato_envio,
            on_decision=self._enviar_decisao)
        self._guardar_conversa()
        self._envio_em_andamento = False
        self._formato_em_uso = False
        self._atualizar_estado_formato()
        if self._sonda_formato:
            formato = self._sonda_formato
            self._sonda_formato = None
            self._registrar_resultado_sonda(response, formato)
            self._agendar_proxima_mensagem()
            return
        self._processar_acoes(response, formato=self._formato_envio)
        self._agendar_proxima_mensagem()

    def _atualizar_resposta_parcial(self, texto):
        if self._formato_envio in ("json", "xml"):
            formato = self._formato_envio.upper()
            self.chat.update_agent(
                f"Recebendo resposta {formato}; será exibida após validação…")
            return
        self.chat.update_agent(texto)

    def _on_send_error(self, error):
        for anexo in self._temporarios_em_voo:
            anexo.descartar()
        self._temporarios_em_voo = []
        self._sonda_formato = None
        self._envio_em_andamento = False
        self._formato_em_uso = False
        self.chat.finish_agent("A troca com o DeepSeek falhou.")
        self.chat.add_system(f"Falha na troca com o DeepSeek: {error}")
        self._atualizar_estado_formato()
        self._atualizar_controles_ocupado()
        self._on_status("Falha no envio", "danger")
        self._agendar_proxima_mensagem()

    def _autorizar_compartilhamento_estrutura(self) -> bool:
        if not (self.project
                and self.project.permissions.requires_read_confirmation):
            return True
        resposta = QMessageBox.question(
            self, "Autorizar compartilhamento da estrutura",
            "O pedido inclui a árvore de arquivos e os caminhos autorizados "
            "do projeto. Enviar essa estrutura ao DeepSeek?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        autorizado = resposta == QMessageBox.StandardButton.Yes
        self.chat.add_system(
            "Estrutura do projeto autorizada para compartilhamento."
            if autorizado else
            "Estrutura do projeto não compartilhada; o pedido seguirá sem o mapa.")
        return autorizado

    def _rodar_agente(self, pedido: str, incluir_mapa=True,
                      anexos_inline=None, arquivos=None):
        worker = AgentWorker(self.controller, self.project, pedido,
                             primeira=self._precisa_regras,
                             instrucoes=self._vault_instructions,
                             formato=self._formato_envio,
                             incluir_mapa=incluir_mapa,
                             anexos=anexos_inline, arquivos=arquivos,
                             habilidades=self._skills_repo)
        self._precisa_regras = False
        self._anexos = []
        self._agente = worker
        self._formato_em_uso = True
        self._atualizar_estado_formato()
        worker.passo_sig.connect(self._agente_passo)
        worker.parcial_sig.connect(self._atualizar_resposta_parcial)
        worker.resposta_sig.connect(self._agente_resposta)
        worker.leitura_sig.connect(self._agente_leitura)
        worker.escrita_sig.connect(self._agente_escrita_aplicada)
        worker.pedir_leitura.connect(
            self._agente_confirmar_leitura,
            Qt.ConnectionType.BlockingQueuedConnection)
        worker.pedir_escrita.connect(
            self._agente_pedir_escrita, Qt.ConnectionType.BlockingQueuedConnection)
        worker.pedir_comando.connect(
            self._agente_pedir_comando, Qt.ConnectionType.BlockingQueuedConnection)
        worker.pedir_decisao.connect(
            self._agente_pedir_decisao,
            Qt.ConnectionType.BlockingQueuedConnection)
        worker.fim_sig.connect(self._agente_fim)
        self.btn_stop.show()
        self._atualizar_controles_ocupado()
        self._on_status("Enviando ao DeepSeek…", "accent")
        self._start(worker)

    def _agente_passo(self, passo):
        self._on_status("Mensagem enviada; aguardando resposta…", "accent")
        self.chat.add_system(f"— rodada {passo.n} —")
        self.chat.start_agent()

    def _agente_resposta(self, passo, lido):
        self.chat.finish_agent(
            passo.resposta,
            lido, formato=self._formato_envio, show_decisions=False)
        self._guardar_conversa()

    def _agente_leitura(self, rel):
        self.chat.add_system(f"leu {rel}")

    def _agente_escrita_aplicada(self, resultados):
        self._atualizar_arvore()
        self.chat.add_system(relatorio(resultados))

    def _agente_confirmar_leitura(self, pedido):
        acao, descricao = pedido
        operacao = {
            "ler": "ler e enviar o conteúdo",
            "listar": "listar e enviar a estrutura",
            "buscar": "buscar e enviar os resultados",
        }.get(acao.verbo, "ler e enviar")
        detalhe = descricao or acao.caminho or "raiz do projeto"
        resposta = QMessageBox.question(
            self, "Autorizar leitura e compartilhamento",
            f"O Agente quer {operacao} em:\n\n{detalhe}\n\n"
            "O resultado será enviado ao DeepSeek. Autorizar?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        autorizado = resposta == QMessageBox.StandardButton.Yes
        self.chat.add_system(
            f"Leitura autorizada: {detalhe}" if autorizado
            else f"Leitura recusada: {detalhe}. Nenhum conteúdo foi enviado.")
        if self._agente:
            self._agente.responder(autorizado)

    def _agente_pedir_escrita(self, planos):
        project = self.project
        if project is None:
            self.chat.add_system("Não há projeto aberto para aplicar as alterações.")
            if self._agente:
                self._agente.responder([])
            return
        if not project.permissions.requires_file_confirmation:
            escolhidos = [
                plano for plano in planos if plano.aplicavel
            ]
            truncados = [
                plano for plano in planos
                if plano.aplicavel and plano.provavel_truncamento
            ]
            if truncados:
                self.chat.add_system(
                    "⚠ Aplicado mesmo com suspeita de truncamento "
                    "(backup salvo): "
                    + ", ".join(plano.rel for plano in truncados)
                    + ". Se o conteúdo parece incompleto, desfaça pelo backup.")
            bloqueados = [plano for plano in planos if not plano.aplicavel]
            if bloqueados:
                self.chat.add_system(
                    relatorio(Executor(project).aplicar(bloqueados)))
            if escolhidos:
                self.chat.add_system(
                    "Alterações autorizadas pelo perfil ativo serão aplicadas "
                    "sem confirmação adicional; cópias de segurança serão mantidas.")
            if self._agente:
                self._agente.responder(escolhidos)
            return
        card = self.chat.add_actions(planos, lambda _c: None)
        card.btn.setEnabled(False)
        card.btn.setText("aguardando revisão…")
        escolhidos = revisar(planos, self)
        if escolhidos:
            card.selar(f"✓ {len(escolhidos)} autorizada(s); aplicando…")
        else:
            card.selar("recusado")
            self.chat.add_system("Alterações recusadas.")
        if self._agente:
            self._agente.responder(escolhidos)

    def _agente_pedir_comando(self, acoes):
        itens = [((a.conteudo or "").strip(), proc_bg.pediu_fundo(a.extras))
                 for a in acoes if (a.conteudo or "").strip()]
        project = self.project
        if project is None:
            self.chat.add_system("Não há projeto aberto para executar comandos.")
            if self._agente:
                self._agente.responder("")
            return
        # `@processos`, `@saida N`, `@parar N` são do app: não vão ao shell nem
        # à confirmação (ADR-025).
        externos = [c for c, _ in itens if proc_bg.comando_interno(c) is None]
        tem_interno = len(externos) != len(itens)
        automatico = not project.permissions.requires_command_confirmation
        if automatico or not externos:
            autorizados = externos
        else:
            autorizados = confirmar_comandos(externos, project.root, self) or []
        if not autorizados and not tem_interno:
            if automatico:
                self.chat.add_system("Nenhum comando válido para executar.")
            else:
                self.chat.add_system("Comando não autorizado.")
            if self._agente:
                self._agente.responder("")
            return
        restantes = list(autorizados)
        saidas = []
        self._parar_comandos = False
        # Garantia: o `responder` é chamado no `finally` — mesmo que algo
        # exploda no meio, o DeepSeek nunca fica pendurado esperando. Cada
        # comando também tem o próprio `try` para o lote continuar rodando
        # quando um falha inesperadamente (o normal vira `Saida.motivo="erro"`
        # dentro do `CommandWorker`).
        try:
            for comando, fundo in itens:
                if self._parar_comandos:
                    saidas.append(
                        f"$ {comando}\n(não executado: você parou o agente)")
                    continue
                try:
                    if proc_bg.comando_interno(comando) is not None:
                        saidas.append(self._comando_interno(comando))
                        continue
                    if comando not in restantes:
                        saidas.append(f"$ {comando}\n(não autorizado por você)")
                        continue
                    restantes.remove(comando)
                    # Comando que não termina sozinho (npm run dev, watch…) sobe
                    # em segundo plano: o agente segue e outros comandos rodam.
                    if fundo or proc_bg.e_continuo(comando):
                        saidas.append(
                            self._rodar_em_segundo_plano(comando, project.root))
                    else:
                        saida = self._rodar_comando_sem_travar(comando, project.root)
                        saidas.append(saida.resumo())
                except Exception as e:
                    saidas.append(
                        f"$ {comando}\n(erro ao executar: {type(e).__name__}: {e})")
        finally:
            if self._agente:
                resposta = ("\n\n".join(saidas) if saidas
                            else "(nenhum comando executado)")
                try:
                    self._agente.responder(resposta)
                except Exception as e:
                    print(f"Falha ao responder comando ao agente: {e}")

    # ---------------- processos em segundo plano (ADR-025) ----------------

    def _gerenciador(self):
        if self._processos is None:
            self._processos = proc_bg.Gerenciador(pasta_logs() / "processos")
        return self._processos

    def _comando_interno(self, comando) -> str:
        nome, numero = proc_bg.comando_interno(comando)
        texto = self._gerenciador().executar_interno(nome, numero)
        self.chat.add_system(texto)
        self._atualizar_botao_processos()
        return texto

    def _rodar_em_segundo_plano(self, comando, cwd) -> str:
        """Sobe o comando, espera ficar pronto sem travar a GUI e devolve o resumo.

        Se o comando terminar durante a espera, ele não era contínuo: vira um
        resultado normal. Se seguir vivo, o card passa a "em segundo plano" e
        continua recebendo a saída por timer até o processo acabar.
        """
        card = self.chat.add_command(comando)
        ger = self._gerenciador()
        try:
            processo = ger.iniciar(comando, cwd)
        except (ComandoRecusado, OSError) as e:
            saida = Saida(comando, -1, f"(comando recusado)\n{e}", motivo="erro")
            card.concluir(saida)
            self.chat.registrar_comando(card.resumo_curto())
            return saida.resumo()
        card.parar_clicked.connect(lambda: (ger.parar(processo.id),
                                            self._atualizar_botao_processos()))
        loop = QEventLoop(self)
        resultado = {}
        curto = (comando.splitlines()[0] if comando else "")[:60]
        inicio = time.monotonic()

        def tick():
            card.tick()
            self._on_status(
                f"Subindo em segundo plano há {int(time.monotonic() - inicio)} s: "
                f"{curto}… (Parar encerra)", "accent")

        relogio = QTimer(self)
        relogio.timeout.connect(tick)
        tick()
        relogio.start(1000)
        worker = EsperaProntoWorker(ger, processo)
        worker.progresso.connect(lambda t: card.receber(t, 0.0))

        def ao_terminar(motivo, pos):
            resultado["motivo"] = motivo
            resultado["pos"] = pos
            loop.quit()

        worker.terminou.connect(ao_terminar)
        self._comando_em_curso = {"proc": processo.proc}
        self._start(worker)
        if "motivo" not in resultado:
            loop.exec()
        relogio.stop()
        relogio.deleteLater()
        self._comando_em_curso = None
        motivo = resultado.get("motivo", "erro")

        if motivo == "terminou" or not processo.vivo():
            interrompido = bool(getattr(processo.proc, "deepseek_interrompido", False))
            codigo = processo.codigo
            saida = Saida(
                comando, -1 if (interrompido or codigo is None) else codigo,
                processo.cauda(20000), interrompido=interrompido,
                motivo="interrompido" if interrompido else "ok",
                segundos=time.monotonic() - inicio)
            card.concluir(saida)
            self.chat.registrar_comando(card.resumo_curto())
            self._atualizar_botao_processos()
            return saida.resumo()

        card.marcar_segundo_plano(processo.id)
        self.chat.registrar_comando(card.resumo_curto())
        self._acompanhar(processo, card, resultado.get("pos", 0))
        self._atualizar_botao_processos()
        explicacao = {
            "pronto": "subiu e avisou que está pronto",
            "silencio": "escreveu e ficou quieto, parece estar no ar",
            "limite": f"ainda subindo depois de {int(proc_bg.ESPERA_MAXIMA_PADRAO)} s",
        }.get(motivo, motivo)
        return (f"$ {comando}\n(rodando em segundo plano: processo {processo.id}, "
                f"pid {processo.pid}; {explicacao}. Continua rodando depois desta "
                "resposta.)\n"
                f"{processo.cauda(3000) or '(sem saída ainda)'}\n\n"
                f"Para ver a saída depois, rode `@saida {processo.id}`; para parar, "
                f"`@parar {processo.id}`; para listar, `@processos`.")

    def _acompanhar(self, processo, card, pos):
        """Leva a saída do log para o card a cada segundo, até o processo acabar."""
        estado = {"pos": pos}
        decodificador = codecs.getincrementaldecoder("utf-8")("replace")
        timer = QTimer(self)

        def ler():
            dados, estado["pos"] = processo.ler_bytes(estado["pos"])
            if dados:
                try:
                    card.anexar(decodificador.decode(dados))
                except RuntimeError:
                    pass  # card apagado (chat limpo)
            if not processo.vivo():
                timer.stop()
                try:
                    card.fim_segundo_plano(processo.codigo)
                except RuntimeError:
                    pass
                self._acompanhamentos.pop(processo.id, None)
                self._atualizar_botao_processos()

        timer.timeout.connect(ler)
        timer.start(1000)
        self._acompanhamentos[processo.id] = timer

    def _atualizar_botao_processos(self):
        vivos = len(self._processos.vivos()) if self._processos is not None else 0
        self.btn_processos.setText(f"Processos ({vivos})" if vivos else "Processos")

    def _montar_menu_processos(self):
        menu = self.btn_processos.menu()
        menu.clear()
        itens = self._processos.listar() if self._processos is not None else []
        if not itens:
            vazio = menu.addAction("Nenhum processo em segundo plano")
            vazio.setEnabled(False)
            return
        for processo in reversed(itens):
            sub = menu.addMenu(processo.linha()[:90])
            abrir = sub.addAction("Abrir log")
            abrir.triggered.connect(
                lambda _=False, p=processo: QDesktopServices.openUrl(
                    QUrl.fromLocalFile(str(p.log))))
            parar = sub.addAction("Parar")
            parar.setEnabled(processo.vivo())
            parar.triggered.connect(
                lambda _=False, p=processo: (self._gerenciador().parar(p.id),
                                             self._atualizar_botao_processos()))
        menu.addSeparator()
        todos = menu.addAction("Parar todos")
        todos.triggered.connect(self._parar_todos_processos)

    def _parar_todos_processos(self):
        if self._processos is not None:
            self._processos.parar_todos()
        self._atualizar_botao_processos()

    def _rodar_comando_sem_travar(self, comando, cwd) -> Saida:
        """Roda um comando com card ao vivo no chat e retorna a `Saida` final.

        Cria um `CommandCard` (barra de status + Parar dedicado + saída ao
        vivo), liga `parar_clicked` a `encerrar(proc)`, e usa `CommandWorker`
        para não bloquear a GUI. O `ao_progredir` do runner chega por sinal,
        então nada do Qt é tocado fora da thread da GUI.

        O status do topo (`lbl_status`) também acompanha o tempo decorrido —
        se você rolou o chat para longe do card, é o único sinal visível.
        """
        card = self.chat.add_command(comando)
        caixa = {}
        loop = QEventLoop(self)
        saida_final = {"saida": None}

        def parar_comando():
            proc = caixa.get("proc")
            if proc is not None:
                encerrar(proc)

        card.parar_clicked.connect(parar_comando)

        curto = (comando.splitlines()[0] if comando else "")[:60]
        inicio = time.monotonic()

        def tick():
            card.tick()
            segundos = int(time.monotonic() - inicio)
            tempo = (f"{segundos // 60} min {segundos % 60:02d} s"
                     if segundos >= 60 else f"{segundos} s")
            self._on_status(
                f"Rodando há {tempo}: {curto}… (Parar encerra)", "accent")

        relogio = QTimer(self)
        relogio.timeout.connect(tick)
        tick()
        relogio.start(1000)

        worker = CommandWorker(
            comando, cwd,
            timeout=TIMEOUT_PADRAO,
            limite_sem_saida=LIMITE_SEM_SAIDA_PADRAO)
        worker.progresso.connect(card.receber)
        worker.iniciou.connect(lambda p: caixa.__setitem__("proc", p))

        def ao_terminar(saida):
            saida_final["saida"] = saida
            card.concluir(saida)
            self.chat.registrar_comando(card.resumo_curto())
            loop.quit()

        worker.terminou.connect(ao_terminar)

        self._comando_em_curso = caixa
        self._start(worker)
        if saida_final["saida"] is None:
            loop.exec()
        relogio.stop()
        relogio.deleteLater()
        self._comando_em_curso = None
        return saida_final["saida"] or Saida(
            comando, -1, "Falha inesperada ao rodar o comando.", motivo="erro")

    def _encerrar_comando_em_curso(self):
        caixa = getattr(self, "_comando_em_curso", None)
        if caixa and caixa.get("proc") is not None:
            encerrar(caixa["proc"])

    def _agente_pedir_decisao(self, acao):
        if self._decision_loop is not None:
            raise RuntimeError("já existe uma decisão aguardando resposta")
        loop = QEventLoop(self)
        escolha = {"valor": None}
        self._decision_loop = loop
        id_remoto = None
        holder = {"card": None}
        escolha["origem"] = "pc"
        escolha["anexos"] = []
        def registrar(valor, origem="local", anexos_resposta=None):
            escolha["valor"] = valor
            escolha["origem"] = "celular" if origem == "celular" else "pc"
            escolha["anexos"] = list(anexos_resposta or [])
            if origem == "celular" and holder["card"] is not None:
                try:
                    holder["card"].marcar_respondido_externo(
                        "celular", valor, escolha["anexos"])
                except RuntimeError:
                    pass
            loop.quit()
        if self.remote:
            id_remoto = self.remote.publish_decision(acao)
            self._decisoes_remotas[id_remoto] = registrar
            self._publicar_estado_remoto()
        def registrar_local(_acao, valor, anexos_resposta=None):
            if id_remoto and self.remote:
                self.remote.mark_resolved(id_remoto, valor)
            registrar(valor, origem="local", anexos_resposta=anexos_resposta)
        self._on_status("Aguardando sua decisão…", "accent")
        card = self.chat.add_decision(acao, registrar_local)
        holder["card"] = card
        loop.exec()
        self._decision_loop = None
        if id_remoto:
            self._decisoes_remotas.pop(id_remoto, None)
            self._publicar_estado_remoto()
        anexos_resposta = escolha["anexos"]
        self.chat.registrar_decisao(
            acao, escolha["valor"], escolha["origem"], anexos_resposta)
        if escolha["valor"] is None and self._agente:
            card.cancel()
            self._agente.parar()
        resposta = escolha["valor"]
        if resposta is not None and anexos_resposta:
            self._temporarios_em_voo = (
                list(self._temporarios_em_voo) + list(anexos_resposta))
            texto, caminhos = _resposta_com_anexos(resposta, anexos_resposta)
            resposta = (texto, caminhos)
        if self._agente:
            self._agente.responder(resposta)
        return escolha["valor"]

    def _enviar_decisao(self, acao, escolha, anexos_resposta=None):
        pergunta = acao.extras["pergunta"]
        self.chat.registrar_decisao(acao, escolha, "pc", anexos_resposta)
        if anexos_resposta:
            if not self.controller.is_connected:
                for anexo in anexos_resposta:
                    anexo.descartar()
                self._on_status("Conecte o navegador primeiro", "danger")
                return
            agente = self.chk_agente.isChecked() and self.project is not None
            mensagem = (f"Minha decisão para “{pergunta}”: {escolha}. "
                        "Veja o(s) anexo(s). Continue a tarefa.")
            self._enfileirar_ou_iniciar(mensagem, agente, list(anexos_resposta))
            return
        rascunho = self.input.toPlainText()
        mensagem = f"Minha decisão para “{pergunta}”: {escolha}. Continue a tarefa."
        self.input.setPlainText(mensagem)
        self._send()
        self.input.setPlainText(rascunho)

    def _agente_fim(self, motivo):
        for anexo in self._temporarios_em_voo:
            anexo.descartar()
        self._temporarios_em_voo = []
        self.chat.add_system(f"◆ {motivo}")
        self._agente = None
        self._formato_em_uso = False
        self.btn_stop.hide()
        self._atualizar_controles_ocupado()
        self._atualizar_estado_formato()
        self.input.setFocus()
        self._on_status(motivo, "success" if "conclu" in motivo else "muted")
        self._agendar_proxima_mensagem()

    def _agendar_proxima_mensagem(self):
        if self._envio_em_andamento or self._agente is not None:
            self._atualizar_feedback_acesso()
            return
        if not self._fila_mensagens:
            self._atualizar_feedback_acesso()
            return
        QTimer.singleShot(0, self._processar_proxima_mensagem)

    def _processar_proxima_mensagem(self):
        if self._envio_em_andamento or self._agente is not None:
            return
        if not self._fila_mensagens:
            self._atualizar_feedback_acesso()
            return
        pedido = self._fila_mensagens.popleft()
        self._fila_mudou()
        self.chat.add_user(pedido[0])
        self._iniciar_pedido(pedido)

    def _parar_agente(self):
        if self._agente:
            self._agente.parar()
            self._parar_comandos = True
            self._encerrar_comando_em_curso()
            if self._decision_loop is not None:
                self._decision_loop.quit()
            self._on_status("Parando no fim da rodada…", "muted")

    def _processar_acoes(self, resposta: str, formato: str | None = None):
        formato = formato or self._formato_envio
        lido = parse(resposta or "", formato=formato)
        if not lido.valida:
            self.chat.add_system(
                f"Resposta {formato.upper()} recusada; nenhuma ação foi aplicada: "
                f"{lido.erro}")
            self._formato_falhou(lido.erro)
            return
        decisoes = [acao for acao in lido.acoes if acao.verbo == "decidir"]
        if decisoes:
            outras_acoes = [acao for acao in lido.acoes if acao.verbo != "decidir"]
            if outras_acoes:
                self.chat.add_system(
                    "A resposta também continha outras ações; nenhuma foi "
                    "executada antes da decisão do usuário.")
            return
        project = self.project
        planos = []
        if lido.tem_acao and project:
            planos = Executor(project).preparar(lido.acoes)
        if planos and project:
            if not project.permissions.requires_file_confirmation:
                auto_aplicaveis = [
                    plano for plano in planos if plano.aplicavel
                ]
                truncados = [
                    plano for plano in planos
                    if plano.aplicavel and plano.provavel_truncamento
                ]
                bloqueados = [plano for plano in planos if not plano.aplicavel]
                resultados = Executor(project).aplicar(
                    auto_aplicaveis + bloqueados)
                self._atualizar_arvore()
                self._atualizar_arvore_vault()
                if any(r.plano.rel.replace("\\", "/") == "vault/AGENTS.md"
                       and r.status == "aplicado" for r in resultados):
                    self._carregar_instrucoes_vault()
                if auto_aplicaveis:
                    self.chat.add_system(
                        "Alterações autorizadas pelo perfil ativo foram "
                        "aplicadas sem confirmação adicional. "
                        "Cópias de segurança foram mantidas.")
                if resultados:
                    self.chat.add_system(relatorio(resultados))
                if truncados:
                    self.chat.add_system(
                        "⚠ Aplicado mesmo com suspeita de truncamento "
                        "(backup salvo): "
                        + ", ".join(plano.rel for plano in truncados)
                        + ". Se o conteúdo parece incompleto, desfaça pelo backup.")
                return
            self.chat.add_actions(planos, self._revisar_acoes)
            return
        if lido.tem_acao and not self.project:
            self.chat.add_system(
                "A Kitty propôs mexer em arquivos, mas não há pasta aberta. "
                "Clique em Abrir pasta e peça de novo.")
        elif lido.suspeita:
            self._formato_falhou()

    def _formato_falhou(self, erro=""):
        if self._tentou_lembrete or not self.controller.is_connected:
            self.chat.add_system(
                "Veio código sem dizer em qual arquivo vai. Copie o bloco na mão, "
                "ou peça de novo dizendo o caminho do arquivo.")
            return
        self._tentou_lembrete = True
        self.chat.add_system("Formato fora do combinado — pedindo para reenviar.")
        if self._formato_envio in ("json", "xml"):
            mensagem = (
                f"A resposta anterior foi inválida: {erro}. Reenvie a resposta "
                "completa usando somente o protocolo abaixo, sem executar "
                "comandos nem alterar arquivos.\n\n"
                + regras_protocolo(self._formato_envio))
        else:
            mensagem = LEMBRETE
        self._enviar_bruto(mensagem)

    def _revisar_acoes(self, card):
        if not self.project:
            self._on_status("Abra uma pasta antes de aplicar", "danger")
            return
        escolhidos = revisar(card.planos, self)
        if not escolhidos:
            self._on_status("Nada aplicado", "muted")
            return
        executor = Executor(self.project)
        resultados = executor.aplicar(escolhidos)
        self._atualizar_arvore()
        aplicados = sum(1 for r in resultados if r.status == "aplicado")
        card.selar(f"✓ {aplicados} aplicada(s)")
        self.chat.add_system(relatorio(resultados))
        tom = "success" if aplicados else "danger"
        self._on_status(f"{aplicados} alteração(ões) aplicada(s)", tom)

    def _open_folder(self):
        pasta = QFileDialog.getExistingDirectory(
            self, "Escolher a pasta do projeto",
            str(self.project.root) if self.project else "")
        if pasta:
            self._set_project(pasta)

    def _open_vault(self):
        if not self.project:
            self._on_status("Abra um projeto antes de vincular o vault", "danger")
            return
        sessao = ProjectSession(self.project.root)
        inicial = sessao.vault_path() or str(self.project.root / "vault")
        pasta = QFileDialog.getExistingDirectory(self, "Escolher o vault do projeto", inicial)
        if not pasta:
            return
        project_root = self.project.root
        project_name = self.project.nome
        self.btn_vault.setEnabled(False)
        self._on_status("Preparando e vinculando o vault…", "muted")
        def preparar():
            try:
                selecionado = Path(pasta).resolve(strict=True)
                if selecionado == project_root:
                    raise SandboxError(
                        "A raiz do projeto não pode ser vinculada como se fosse "
                        "o próprio vault.")
                caminho = garantir_vault(selecionado, project_name)
                if not ProjectSession(project_root).salvar_vault(str(caminho)):
                    raise OSError("Não consegui salvar o vínculo do vault no projeto.")
                return str(caminho), ""
            except (OSError, SandboxError, ValueError) as error:
                return "", str(error)
        self._bg(
            preparar,
            lambda resultado: self._vault_preparado(project_root, pasta, resultado))

    def _vault_preparado(self, project_root, selecionado, resultado):
        if not self.project or self.project.root != project_root:
            return
        self.btn_vault.setEnabled(True)
        caminho, erro = resultado or ("", "A tarefa de preparação do vault falhou.")
        if erro:
            self._on_status(
                f"Não consegui preparar o vault {selecionado}: {erro}", "danger")
            return
        self.project.vault_root = Path(caminho)
        if self._carregar_instrucoes_vault():
            self._on_status(f"Vault preparado e vinculado: {caminho}", "success")
        self._atualizar_controles_ocupado()

    def _configurar_permissoes(self):
        if not self.project:
            self._on_status("Abra um projeto antes de configurar permissões", "danger")
            return
        dialogo = PermissionDialog(self.project, self)
        if dialogo.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            politica = PermissionPolicy.from_dict(self.project.root, dialogo.settings())
        except (ValueError, SandboxError) as e:
            self._on_status(f"Configuração de acesso recusada: {e}", "danger")
            return
        sessao = ProjectSession(self.project.root)
        if not sessao.salvar_permissoes(politica.to_dict()):
            self._on_status("Não consegui salvar as permissões deste projeto", "danger")
            return
        self.project.permissions = politica
        self.project.sandbox = politica.project
        self._atualizar_feedback_acesso()
        self._on_status(f"Permissões atualizadas: {politica.mode}", "success")

    def _atualizar_feedback_acesso(self):
        if not self.project:
            self.lbl_access_summary.setText("Acesso: sem projeto")
            self.lbl_access_summary.setToolTip(
                "Abra um projeto e use o botão Acesso para definir o escopo.")
        else:
            politica = self.project.permissions
            nomes = {
                "project_confirm": "Projeto · confirmar alterações",
                "project_auto": "Projeto + vault · automático",
                "folders": (
                    f"Pastas escolhidas ({len(politica.grants)}) · grants por operação"),
                "computer_confirm": "Computador · confirmar alterações",
                "computer_auto": "Computador · automático",
            }
            leitura = ("confirma leitura/envio" if politica.requires_read_confirmation
                       else "leitura automática")
            self.lbl_access_summary.setText(
                f"Acesso: {nomes[politica.mode]} · {leitura}")
            tooltip = "Use o botão Acesso para escopo/grants. " + (
                    "Cada pedido de leitura/listagem/busca pergunta antes de "
                    "compartilhar o resultado com o DeepSeek."
                    if politica.requires_read_confirmation else
                    "Leituras do agente são compartilhadas sem confirmação.")
            if politica.mode == "folders":
                descricoes = []
                rotulos = {
                    "read": "ler", "create": "criar",
                    "edit": "editar", "delete": "apagar",
                }
                for grant in politica.grants:
                    operacoes = [rotulo for chave, rotulo in rotulos.items()
                                 if grant[chave]]
                    descricoes.append(
                        f"{grant['path']}: {', '.join(operacoes) or 'nenhuma operação'}")
                tooltip += "\n\nGrants por pasta:\n" + (
                    "\n".join(descricoes) if descricoes else "Nenhuma pasta autorizada.")
            self.lbl_access_summary.setToolTip(tooltip)
        pendentes = len(self._fila_mensagens)
        self.lbl_queue.setText(f"Fila: {pendentes}" if pendentes else "")
        self._atualizar_controles_ocupado()

    def _atualizar_controles_ocupado(self):
        ocupado = (self._envio_em_andamento or self._agente is not None
                   or bool(self._fila_mensagens))
        self.btn_send.setText("Enfileirar" if ocupado else "Enviar")
        self.input.setEnabled(self.controller.is_connected)
        self.btn_send.setEnabled(self.controller.is_connected)
        for controle in (self.btn_folder, self.btn_vault, self.btn_permissions,
                         self.btn_new, self.btn_history, self.cmb_formato):
            controle.setEnabled(not ocupado)
        projeto_ok = self.project is not None and not ocupado
        for controle in (self.btn_project_folder, self.btn_project_file,
                         self.btn_project_refresh):
            controle.setEnabled(projeto_ok)
        vault_ok = (projeto_ok and bool(
            self.project and self.project.vault_root
            and Path(self.project.vault_root).is_dir()))
        for controle in (self.btn_vault_note, self.btn_vault_folder,
                         self.btn_vault_refresh, self.btn_vault_explorer):
            controle.setEnabled(vault_ok)
        self._publicar_estado_remoto()

    def _carregar_instrucoes_vault(self):
        if not self.project:
            self.lbl_vault_path.setText("Nenhum vault vinculado")
            self._vault_instructions = ""
            self.vault_tree.clear()
            for botao in (self.btn_vault_explorer, self.btn_vault_note,
                          self.btn_vault_folder, self.btn_vault_refresh):
                botao.setEnabled(False)
            return True
        caminho = ProjectSession(self.project.root).vault_path()
        if not caminho:
            self.lbl_vault_path.setText("Nenhum vault vinculado")
            self._vault_instructions = ""
            self.vault_tree.clear()
            self._atualizar_arvore_vault()
            return True
        pasta = Path(caminho)
        self.lbl_vault_path.setText(str(pasta))
        if not pasta.is_dir():
            self._vault_instructions = ""
            self.project.vault_root = None
            self._atualizar_arvore_vault()
            self._on_status(f"O vault vinculado não foi encontrado: {pasta}", "danger")
            return False
        self.project.vault_root = pasta.resolve(strict=True)
        arquivo = pasta / "AGENTS.md"
        try:
            texto = arquivo.read_text(encoding="utf-8") if arquivo.is_file() else ""
        except (OSError, UnicodeError) as e:
            self._vault_instructions = ""
            self._on_status(f"Não consegui ler {arquivo}: {e}", "danger")
            return False
        self._vault_instructions = texto
        self._atualizar_arvore_vault()
        return True

    def _abrir_vault_no_explorer(self):
        if not self.project:
            self._on_status("Abra um projeto primeiro", "danger")
            return
        caminho = ProjectSession(self.project.root).vault_path()
        if not caminho or not os.path.isdir(caminho):
            self._on_status("Vincule um vault existente primeiro", "danger")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(caminho))

    def _store_workspace(self, tipo):
        if not self.project:
            raise SandboxError("Abra um projeto primeiro.")
        if tipo == "projeto":
            return WorkspaceStore(
                self.project.root, self.project.root, project_tree=True)
        caminho = ProjectSession(self.project.root).vault_path()
        if not caminho or not Path(caminho).is_dir():
            raise SandboxError("Nenhum vault válido está vinculado ao projeto.")
        return WorkspaceStore(
            caminho, self.project.root, backup_prefix="_vault")

    def _preencher_arvore(self, tree, entries, tipo):
        tree.clear()
        self._tree_fill_generation[tipo] += 1
        generation = self._tree_fill_generation[tipo]
        entries = list(entries)
        itens = {}
        batch_size = 250
        def preencher_lote(inicio):
            if generation != self._tree_fill_generation[tipo]:
                return
            fim = min(inicio + batch_size, len(entries))
            for entrada in entries[inicio:fim]:
                partes = entrada.path.split("/")
                pai = None
                caminho = ""
                for indice, parte in enumerate(partes):
                    caminho = f"{caminho}/{parte}".strip("/")
                    item = itens.get(caminho)
                    if item is None:
                        item = QTreeWidgetItem([parte])
                        item.setData(0, Qt.ItemDataRole.UserRole, caminho)
                        is_dir = indice < len(partes) - 1 or entrada.is_dir
                        item.setData(0, Qt.ItemDataRole.UserRole + 1, is_dir)
                        if pai is None:
                            tree.addTopLevelItem(item)
                        else:
                            pai.addChild(item)
                        itens[caminho] = item
                    pai = item
            if fim < len(entries):
                QTimer.singleShot(0, lambda: preencher_lote(fim))
        preencher_lote(0)

    def _atualizar_arvore(self):
        if not self.project:
            self.project_tree.clear()
            self.lbl_tree_project.setText("Nenhum projeto aberto")
            return
        root = self.project.root
        self.lbl_tree_project.setText(str(root))
        self._tree_scan_generation["projeto"] += 1
        generation = self._tree_scan_generation["projeto"]
        def listar():
            try:
                return self._workspace_entries(root, projeto=True), ""
            except (OSError, SandboxError, RecursionError) as error:
                return [], str(error)
        self._bg(
            listar,
            lambda resultado: self._arvore_listada(
                "projeto", root, generation, resultado))

    def _workspace_entries(self, root, projeto=False, backup_root=None):
        if projeto:
            return WorkspaceStore(root, root, project_tree=True).entries()
        return WorkspaceStore(
            root, backup_root or root, backup_prefix="_vault").entries()

    def _arvore_listada(self, tipo, root, generation, resultado):
        if generation != self._tree_scan_generation[tipo] or not self.project:
            return
        if tipo == "projeto":
            valido = self.project.root == root
            tree = self.project_tree
        else:
            vinculo = ProjectSession(self.project.root).vault_path()
            valido = vinculo and Path(vinculo).resolve() == root
            tree = self.vault_tree
        if not valido:
            return
        entradas, erro = resultado or ([], "Não foi possível ler a árvore.")
        if erro:
            self._on_status(f"Não consegui atualizar a árvore de {tipo}: {erro}", "danger")
            return
        self._preencher_arvore(tree, entradas, tipo)

    def _atualizar_arvore_vault(self):
        project = self.project
        caminho = ProjectSession(project.root).vault_path() if project else None
        if not caminho:
            self.vault_tree.clear()
            self.lbl_vault_path.setText("Nenhum vault vinculado")
            self.btn_vault_explorer.setEnabled(False)
            for botao in (self.btn_vault_note, self.btn_vault_folder,
                          self.btn_vault_refresh):
                botao.setEnabled(False)
            return
        self.lbl_vault_path.setText(str(caminho))
        valido = Path(caminho).is_dir()
        self.btn_vault_explorer.setEnabled(valido)
        for botao in (self.btn_vault_note, self.btn_vault_folder,
                      self.btn_vault_refresh):
            botao.setEnabled(valido)
        if not valido:
            self.vault_tree.clear()
            return
        root = Path(caminho).resolve()
        project_root = project.root
        self._tree_scan_generation["vault"] += 1
        generation = self._tree_scan_generation["vault"]
        def listar():
            try:
                return self._workspace_entries(
                    root, backup_root=project_root), ""
            except (OSError, SandboxError, RecursionError) as error:
                return [], str(error)
        self._bg(
            listar,
            lambda resultado: self._arvore_listada(
                "vault", root, generation, resultado))

    def _pasta_selecionada(self, tipo):
        tree = self.project_tree if tipo == "projeto" else self.vault_tree
        item = tree.currentItem()
        if item is None:
            return ""
        rel = item.data(0, Qt.ItemDataRole.UserRole)
        is_dir = item.data(0, Qt.ItemDataRole.UserRole + 1)
        return rel if is_dir else str(Path(rel).parent).replace("\\", "/")

    def _menu_workspace(self, tipo, pos):
        tree = self.project_tree if tipo == "projeto" else self.vault_tree
        item = tree.itemAt(pos)
        if item is not None:
            tree.setCurrentItem(item)
        menu = QMenu(self)
        menu.addAction("Nova pasta", lambda: self._criar_pasta_workspace(tipo))
        if tipo == "vault":
            menu.addAction("Nova nota…", self._criar_nota_vault)
        else:
            menu.addAction("Novo arquivo…",
                           lambda: self._criar_arquivo_workspace(tipo))
        if item is not None:
            is_dir = bool(item.data(0, Qt.ItemDataRole.UserRole + 1))
            if not is_dir:
                menu.addAction("Editar…",
                               lambda: self._abrir_item_workspace(tipo, item))
            menu.addSeparator()
            menu.addAction("Excluir…",
                           lambda: self._excluir_item_workspace(tipo, item))
        menu.addSeparator()
        menu.addAction("Atualizar", self._atualizar_arvore
                       if tipo == "projeto" else self._atualizar_arvore_vault)
        menu.exec(tree.viewport().mapToGlobal(pos))

    def _criar_pasta_workspace(self, tipo):
        inicial = self._pasta_selecionada(tipo)
        nome, ok = QInputDialog.getText(self, "Nova pasta", "Nome da pasta:")
        if not ok or not nome.strip():
            return
        rel = f"{inicial}/{nome.strip()}".strip("/")
        try:
            self._store_workspace(tipo).create_folder(rel)
        except (OSError, SandboxError, ValueError) as e:
            self._on_status(f"Não consegui criar a pasta: {e}", "danger")
            return
        self._atualizar_arvore()
        if tipo == "vault":
            self._atualizar_arvore_vault()
        self._on_status(f"Pasta criada: {rel}", "success")

    def _criar_arquivo_workspace(self, tipo):
        pasta = self._pasta_selecionada(tipo)
        extensao = ".md" if tipo == "vault" else ".txt"
        nome, ok = QInputDialog.getText(
            self, "Novo arquivo", f"Nome do arquivo ({extensao} por padrão):")
        if not ok or not nome.strip():
            return
        if not Path(nome).suffix:
            nome = nome.strip() + extensao
        rel = f"{pasta}/{nome.strip()}".strip("/")
        dialogo = TextFileDialog("Novo arquivo", rel, "", self)
        if dialogo.exec() != QDialog.DialogCode.Accepted:
            return
        self._gravar_arquivo_workspace(tipo, rel, dialogo.text(), criar=True)

    def _criar_nota_vault(self):
        inicial = self._pasta_selecionada("vault") or "Notas"
        dialogo = NewNoteDialog(inicial, self)
        if dialogo.exec() != QDialog.DialogCode.Accepted:
            return
        dados = dialogo.details()
        try:
            nome = nome_arquivo_seguro(dados["title"])
            pasta = dados["folder"].replace("\\", "/").strip("/")
            rel = f"{pasta}/{nome}.md".strip("/")
            texto = conteudo_nota(
                dados["title"], dados["type"], dados["tags"],
                dados["context"], dados["content"])
        except ValueError as e:
            self._on_status(str(e), "danger")
            return
        self._gravar_arquivo_workspace("vault", rel, texto, criar=True)

    def _gravar_arquivo_workspace(self, tipo, rel, texto, criar=False):
        if tipo == "vault" and not criar:
            texto = atualizar_data_nota(texto)
        try:
            self._store_workspace(tipo).write_text(rel, texto, create=criar)
        except (OSError, SandboxError, ValueError) as e:
            self._on_status(f"Não consegui salvar {rel}: {e}", "danger")
            return
        self._atualizar_arvore()
        if tipo == "vault":
            if rel.replace("\\", "/") == "AGENTS.md":
                self._carregar_instrucoes_vault()
            else:
                self._atualizar_arvore_vault()
        self._on_status(f"Arquivo salvo: {rel}", "success")

    def _abrir_item_workspace(self, tipo, item):
        rel = item.data(0, Qt.ItemDataRole.UserRole)
        if item.data(0, Qt.ItemDataRole.UserRole + 1):
            item.setExpanded(not item.isExpanded())
            return
        try:
            texto = self._store_workspace(tipo).read_text(rel)
        except (OSError, SandboxError, ValueError) as e:
            self._on_status(f"Não consegui abrir {rel}: {e}", "danger")
            return
        dialogo = TextFileDialog("Editar arquivo", rel, texto, self)
        if dialogo.exec() == QDialog.DialogCode.Accepted:
            self._gravar_arquivo_workspace(tipo, rel, dialogo.text())

    def _excluir_item_workspace(self, tipo, item):
        rel = item.data(0, Qt.ItemDataRole.UserRole)
        is_dir = bool(item.data(0, Qt.ItemDataRole.UserRole + 1))
        descricao = "a pasta e todo o seu conteúdo" if is_dir else "o arquivo"
        resposta = QMessageBox.question(
            self, "Confirmar exclusão",
            f"Excluir {descricao}?\n\n{rel}\n\n"
            "O item será movido para o backup do projeto e poderá ser recuperado.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if resposta != QMessageBox.StandardButton.Yes:
            return
        try:
            self._store_workspace(tipo).delete(rel)
        except (OSError, SandboxError, ValueError) as e:
            self._on_status(f"Não consegui excluir {rel}: {e}", "danger")
            return
        self._atualizar_arvore()
        if tipo == "vault":
            if rel.replace("\\", "/") == "AGENTS.md":
                self._carregar_instrucoes_vault()
            else:
                self._atualizar_arvore_vault()
        self._on_status(f"Movido para backup: {rel}", "success")

    def _set_project(self, caminho, avisar=True):
        """Troca a pasta autorizada. É a única porta para o disco."""
        permissoes_ok = True
        try:
            try:
                permissoes = PermissionPolicy.from_dict(
                    caminho, ProjectSession(caminho).permissoes())
            except (ValueError, SandboxError) as e:
                permissoes_ok = False
                self._on_status(
                    f"Permissões salvas inválidas; usando modo restrito: {e}",
                    "danger")
                permissoes = PermissionPolicy(caminho)
            self.project = Project(caminho, permissoes)
        except (SandboxError, OSError, ValueError) as e:
            self.project = None
            self._skills_repo = None
            self.skills_view.set_repo(None)
            self._on_status(f"Pasta recusada: {e}", "danger")
            self._refresh_project_label()
            self._atualizar_arvore()
            self._carregar_instrucoes_vault()
            self._carregar_formato_projeto()
            self._atualizar_feedback_acesso()
            return
        salvar_raiz(str(self.project.root))
        self._refresh_project_label()
        self._atualizar_arvore()
        self._skills_repo = SkillsRepo(self.project.root)
        self.skills_view.set_repo(self._skills_repo)
        sessao = ProjectSession(self.project.root)
        self._carregar_formato_projeto()
        self._atualizar_feedback_acesso()
        vinculo_ok = True
        caminho_vault = sessao.vault_path()
        try:
            if caminho_vault:
                if not Path(caminho_vault).is_dir():
                    raise FileNotFoundError(
                        f"O vault vinculado não foi encontrado: {caminho_vault}")
                if Path(caminho_vault).resolve(strict=True) == self.project.root:
                    raise SandboxError(
                        "A raiz do projeto não pode ser usada como raiz do vault.")
                caminho_vault = garantir_vault(caminho_vault, self.project.nome)
            else:
                caminho_vault = garantir_vault(
                    self.project.root / "vault", self.project.nome)
                if not sessao.salvar_vault(str(caminho_vault)):
                    vinculo_ok = False
                    raise OSError("Não consegui salvar o vínculo do vault no projeto.")
            self.project.vault_root = caminho_vault
        except (OSError, SandboxError, ValueError) as e:
            vinculo_ok = False
            self.project.vault_root = None
            self._on_status(f"Não consegui preparar o vault do projeto: {e}", "danger")
        vault_ok = self._carregar_instrucoes_vault()
        self._atualizar_arvore()
        self.terminal.definir_cwd(self.project.root)
        self._atualizar_controles_ocupado()
        if avisar and vault_ok and vinculo_ok and permissoes_ok:
            n = len(self.project.arquivos())
            self._on_status(f"Pasta aberta: {self.project.nome} ({n} arquivos)", "success")
        if self.controller.is_connected:
            self._precisa_regras = True
            self.chat.clear()
            self._retomar_conversa()

    def _refresh_project_label(self):
        if self.project:
            self.lbl_project.setText(f"📁 {self.project.nome}")
            self.lbl_project.setToolTip(
                f"Raiz do projeto:\n{self.project.root}\n\n"
                f"Perfil de acesso: {self.project.permissions.mode}\n"
                "Use Acesso para configurar escopo e permissões.")
        else:
            self.lbl_project.setText("nenhuma pasta aberta")
            self.lbl_project.setToolTip(
                "Nenhuma pasta autorizada: a Kitty não pode tocar em arquivo.")

    def closeEvent(self, event):
        self._parar_updater()
        if self.remote is not None:
            try:
                self.remote.stop()
            except Exception:
                pass
            self.remote = None
        for timer in list(self._acompanhamentos.values()):
            timer.stop()
        self._acompanhamentos.clear()
        if self._processos is not None:
            # Servidor de dev aberto pelo agente não fica órfão (ADR-025).
            self._processos.parar_todos()
        self.terminal.parar()
        for anexo in self._temporarios_em_voo:
            anexo.descartar()
        self._temporarios_em_voo = []
        for pedido in self._fila_mensagens:
            for anexo in pedido[3]:
                anexo.descartar()
        self._fila_mensagens.clear()
        self._parar_comandos = True
        self._encerrar_comando_em_curso()
        if self._decision_loop is not None:
            self._decision_loop.quit()
        if self._agente is not None:
            self._agente.abortar()
            self._agente.wait(3000)
            self._agente = None
        try:
            self.controller.disconnect()
        except Exception:
            pass
        super().closeEvent(event)
