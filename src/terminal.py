"""Terminal embutido — o seu, não o da Kitty.

Serve para você olhar a pasta, rodar um `git status`, abrir um arquivo, sem sair
do app para o Explorer.

**Isto não é o `runner.py`** (onde rodam os comandos que o *modelo* pede, com a
confirmação do perfil de Acesso). Aqui quem digita é você, na sua máquina, sem
trava nenhuma. O agente nunca escreve neste painel — ele não tem acesso a este
objeto.

Cada aba é um `cmd.exe` persistente, então `cd` funciona como você espera. Um
comando que não termina (`npm run dev`) ocupa só a aba dele: abra outra com
**+ aba** e siga trabalhando ([[ADR-025 Comandos contínuos em segundo plano]]).
**interromper** encerra o comando que está rodando na aba e mantém o shell.
A saída vem em cp850/cp1252 no Windows, daí a decodificação tolerante.
"""

import locale
import os
import subprocess

from PyQt6.QtCore import QProcess, Qt, pyqtSignal
from PyQt6.QtGui import QTextCursor
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QTabWidget,
    QToolButton,
    QVBoxLayout,
)

from src.theme import Color

MAX_LINHAS = 4000
_SEM_JANELA = getattr(subprocess, "CREATE_NO_WINDOW", 0)
# Filhos do shell que não são o comando do usuário: matar quebraria o shell.
_FILHOS_DO_SHELL = {"conhost.exe"}


def _shell():
    """(programa, args) do shell interativo desta plataforma."""
    if os.name == "nt":
        return os.environ.get("COMSPEC", "cmd.exe"), ["/Q", "/K", "prompt $P$G"]
    return os.environ.get("SHELL", "/bin/bash"), ["-i"]


def filhos_do_processo(pid: int) -> list[int]:
    """PIDs dos processos filhos diretos de `pid` (sem o conhost do shell)."""
    if not pid:
        return []
    if os.name != "nt":
        try:
            r = subprocess.run(["pgrep", "-P", str(pid)], capture_output=True,
                               text=True, timeout=10)
            return [int(x) for x in r.stdout.split()]
        except (OSError, subprocess.TimeoutExpired, ValueError):
            return []
    consulta = (f"Get-CimInstance Win32_Process -Filter 'ParentProcessId={int(pid)}' | "
                "ForEach-Object { \"$($_.ProcessId);$($_.Name)\" }")
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-Command", consulta],
                           capture_output=True, text=True, timeout=15,
                           creationflags=_SEM_JANELA)
    except (OSError, subprocess.TimeoutExpired):
        return []
    pids = []
    for linha in r.stdout.splitlines():
        numero, _, nome = linha.strip().partition(";")
        if numero.isdigit() and nome.strip().lower() not in _FILHOS_DO_SHELL:
            pids.append(int(numero))
    return pids


class SessaoShell(QFrame):
    """Um shell persistente: saída, campo de entrada e histórico próprios."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.cwd = None
        self._historico = []
        self._pos_hist = 0
        self.proc = None

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        self.saida = QPlainTextEdit()
        self.saida.setObjectName("terminalSaida")
        self.saida.setReadOnly(True)
        self.saida.setMaximumBlockCount(MAX_LINHAS)
        self.saida.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.saida.setFrameShape(QFrame.Shape.NoFrame)
        lay.addWidget(self.saida, 1)

        self.entrada = QLineEdit()
        self.entrada.setObjectName("terminalEntrada")
        self.entrada.setPlaceholderText("comando…   ↑ ↓ navega o histórico")
        self.entrada.returnPressed.connect(self._enviar)
        self.entrada.installEventFilter(self)
        lay.addWidget(self.entrada)

    # ---------------- ciclo de vida ----------------

    def _vivo(self) -> bool:
        return self.proc is not None and self.proc.state() != QProcess.ProcessState.NotRunning

    def iniciar(self):
        if self._vivo() or not self.cwd:
            return
        programa, args = _shell()
        self.proc = QProcess(self)
        self.proc.setWorkingDirectory(self.cwd)
        self.proc.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self.proc.readyReadStandardOutput.connect(self._ler)
        self.proc.finished.connect(
            lambda code, _s: self._escrever(f"\n[shell encerrado, código {code}]\n"))
        self.proc.errorOccurred.connect(
            lambda _e: self._escrever(f"\n[falha no shell: {self.proc.errorString()}]\n"))
        self.proc.start(programa, args)

    def reiniciar(self):
        self.parar()
        self.saida.clear()
        if self.cwd:
            self.iniciar()
        else:
            self._escrever("Abra uma pasta para usar o terminal.\n")

    def parar(self):
        if self._vivo():
            # Derruba também o que o shell abriu (um `npm run dev` não fica órfão).
            pid = int(self.proc.processId() or 0)
            if os.name == "nt" and pid:
                subprocess.run(["taskkill", "/T", "/F", "/PID", str(pid)],
                               capture_output=True, creationflags=_SEM_JANELA)
            self.proc.kill()
            self.proc.waitForFinished(1500)
        self.proc = None

    def interromper(self) -> int:
        """Encerra o comando rodando nesta aba e mantém o shell. Devolve quantos."""
        if not self._vivo():
            return 0
        filhos = filhos_do_processo(int(self.proc.processId() or 0))
        for pid in filhos:
            if os.name == "nt":
                subprocess.run(["taskkill", "/T", "/F", "/PID", str(pid)],
                               capture_output=True, creationflags=_SEM_JANELA)
            else:
                try:
                    os.kill(pid, 15)
                except OSError:
                    pass
        self._escrever("\n[comando interrompido]\n" if filhos
                       else "\n[nada rodando nesta aba]\n")
        return len(filhos)

    def limpar(self):
        self.saida.clear()

    # ---------------- entrada e saída ----------------

    def _enviar(self):
        comando = self.entrada.text()
        if not comando.strip():
            return
        if not self._vivo():
            self.iniciar()
        if not self._vivo():
            self._escrever("[shell não está rodando]\n")
            return
        self._historico.append(comando)
        self._pos_hist = len(self._historico)
        self.entrada.clear()
        self.proc.write((comando + os.linesep).encode(self._codec(), errors="replace"))

    @staticmethod
    def _codec() -> str:
        return locale.getpreferredencoding(False) or "utf-8"

    def _ler(self):
        dados = bytes(self.proc.readAllStandardOutput())
        if dados:
            self._escrever(dados.decode(self._codec(), errors="replace"))

    def _escrever(self, texto: str):
        # Rolagem só acompanha se você já estava no fim — senão, ler saída
        # antiga enquanto o comando cospe linhas seria impossível.
        barra = self.saida.verticalScrollBar()
        colado = barra.value() >= barra.maximum() - 4
        self.saida.moveCursor(QTextCursor.MoveOperation.End)
        self.saida.insertPlainText(texto)
        if colado:
            barra.setValue(barra.maximum())

    # ---------------- histórico com as setas ----------------

    def eventFilter(self, obj, event):
        if obj is self.entrada and event.type() == event.Type.KeyPress:
            if event.key() == Qt.Key.Key_Up:
                self._andar_hist(-1)
                return True
            if event.key() == Qt.Key.Key_Down:
                self._andar_hist(1)
                return True
        return super().eventFilter(obj, event)

    def _andar_hist(self, passo):
        if not self._historico:
            return
        self._pos_hist = max(0, min(len(self._historico), self._pos_hist + passo))
        self.entrada.setText(
            "" if self._pos_hist >= len(self._historico)
            else self._historico[self._pos_hist])
        self.entrada.setCursorPosition(len(self.entrada.text()))


class Terminal(QFrame):
    """Painel de terminal preso à raiz do projeto, com uma aba por shell.

    A interface antiga (`saida`, `entrada`, `proc`, `_enviar`, `_vivo`,
    `_historico`, `_andar_hist`) aponta para a aba ativa.
    """

    fechado = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("terminal")
        self.cwd = None
        self._numero = 0

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        cabeca = QFrame()
        cabeca.setObjectName("terminalHeader")
        h = QHBoxLayout(cabeca)
        h.setContentsMargins(10, 4, 4, 4)
        h.setSpacing(8)
        self.lbl_cwd = QLabel("terminal")
        self.lbl_cwd.setObjectName("terminalCwd")
        h.addWidget(self.lbl_cwd)
        h.addStretch(1)

        for texto, dica, fn in (
                ("+ aba", "Abre outro shell: um comando contínuo (npm run dev) não trava os outros",
                 self.nova_aba),
                ("interromper", "Encerra o comando rodando nesta aba e mantém o shell",
                 self.interromper),
                ("limpar", "Limpa a tela desta aba", self.limpar),
                ("reiniciar", "Fecha e abre o shell desta aba de novo", self.reiniciar),
                ("✕", "Esconde o terminal", self.fechado.emit)):
            b = QToolButton()
            b.setObjectName("codeAction")
            b.setText(texto)
            b.setToolTip(dica)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(fn)
            h.addWidget(b)
        lay.addWidget(cabeca)

        self.abas = QTabWidget()
        self.abas.setObjectName("terminalAbas")
        self.abas.setDocumentMode(True)
        self.abas.setTabsClosable(True)
        self.abas.setMovable(True)
        self.abas.tabCloseRequested.connect(self.fechar_aba)
        lay.addWidget(self.abas, 1)
        self._criar_aba()

    # ---------------- abas ----------------

    def _criar_aba(self) -> SessaoShell:
        self._numero += 1
        sessao = SessaoShell(self)
        sessao.cwd = self.cwd
        indice = self.abas.addTab(sessao, f"shell {self._numero}")
        self.abas.setCurrentIndex(indice)
        return sessao

    def nova_aba(self):
        sessao = self._criar_aba()
        if self.cwd:
            sessao.iniciar()
        else:
            sessao._escrever("Abra uma pasta para usar o terminal.\n")
        sessao.entrada.setFocus()
        return sessao

    def fechar_aba(self, indice: int):
        sessao = self.abas.widget(indice)
        if sessao is None:
            return
        if self.abas.count() == 1:
            sessao.reiniciar()  # sempre fica uma aba
            return
        sessao.parar()
        self.abas.removeTab(indice)
        sessao.deleteLater()

    def sessoes(self) -> list[SessaoShell]:
        return [self.abas.widget(i) for i in range(self.abas.count())]

    @property
    def atual(self) -> SessaoShell:
        return self.abas.currentWidget()

    # ---------------- interface antiga, na aba ativa ----------------

    @property
    def saida(self):
        return self.atual.saida

    @property
    def entrada(self):
        return self.atual.entrada

    @property
    def proc(self):
        return self.atual.proc

    @property
    def _historico(self):
        return self.atual._historico

    def _vivo(self) -> bool:
        return self.atual._vivo()

    def _enviar(self):
        self.atual._enviar()

    def _andar_hist(self, passo):
        self.atual._andar_hist(passo)

    def _escrever(self, texto: str):
        self.atual._escrever(texto)

    # ---------------- ciclo de vida ----------------

    def definir_cwd(self, caminho):
        """Aponta o terminal para a pasta do projeto e (re)inicia o shell.

        Pasta nova fecha as abas extras: shells da pasta anterior não servem mais.
        """
        novo = str(caminho) if caminho else None
        if novo == self.cwd and self._vivo():
            return
        self.cwd = novo
        self.lbl_cwd.setText(novo or "terminal (sem pasta aberta)")
        while self.abas.count() > 1:
            sessao = self.abas.widget(self.abas.count() - 1)
            sessao.parar()
            self.abas.removeTab(self.abas.count() - 1)
            sessao.deleteLater()
        self.abas.setCurrentIndex(0)
        self.atual.cwd = novo
        self.reiniciar()

    def iniciar(self):
        self.atual.cwd = self.cwd
        self.atual.iniciar()

    def reiniciar(self):
        self.atual.cwd = self.cwd
        self.atual.reiniciar()

    def interromper(self):
        return self.atual.interromper()

    def parar(self):
        """Encerra todos os shells (ao fechar o app)."""
        for sessao in self.sessoes():
            sessao.parar()

    def limpar(self):
        self.atual.limpar()
