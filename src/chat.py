"""Painel de chat: bolha do usuário à direita, resposta do DeepSeek à esquerda.

O texto que chega do wrapper é Markdown. Aqui ele é quebrado em blocos de texto
e blocos de código (cercas ```), e cada tipo vira um widget: o texto vira QLabel
com um subconjunto de Markdown convertido para rich text, e o código vira um
card com a linguagem no cabeçalho e botão de copiar.

Também mantém um `historico` em memória — lista de mensagens como o painel
remoto (celular) precisa. Cada item tem `role`, `content` e `ts`. `streaming`
expõe o parcial em curso para o mesmo painel acompanhar a resposta ao vivo.

O `historico` guarda o texto **amigável** — não o envelope cru. Quando o
projeto está em modo JSON/XML e a resposta é válida, o card visível mostra
`resposta.resumo`; o histórico tem que ter o mesmo, senão o painel remoto
recebe `{"response": …}` cru e mostra como texto.
"""

import html
import re
import time
from pathlib import PurePosixPath

from PyQt6.QtCore import QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QGuiApplication, QPalette, QTextCursor
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStyle,
    QStyleOptionToolButton,
    QStylePainter,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from src import anexos
from src.parser import parse
from src.theme import TONE, Color

FENCE_RE = re.compile(r"```([^\n`]*)\n(.*?)(?:```|\Z)", re.DOTALL)


def _ts() -> str:
    return time.strftime("%H:%M:%S", time.localtime())


def texto_amigavel(md: str, resposta, formato: str) -> str:
    """O que o card **mostra** vira o que o histórico guarda.

    Em Markdown/`kitty`, é o `md` inteiro. Em JSON/XML válidos, é só o
    `resposta.resumo` — o envelope é consumido na hora e o painel remoto
    não tem como saber que precisa decodificar.

    Resposta inválida (parse falhou) fica com o próprio `md`; o card mostra
    "resposta inválida" + o cru num card de código, e o histórico precisa
    refletir isso.
    """
    if resposta is not None and getattr(resposta, "valida", False):
        resumo = getattr(resposta, "resumo", "") or ""
        if formato in ("json", "xml"):
            return resumo
        return md or ""
    return md or ""


def split_markdown(md: str):
    """Quebra o Markdown em [('text'|'code', conteúdo, linguagem), ...].

    A última cerca pode estar aberta (o streaming ainda não fechou o ```), por
    isso o `\\Z` no regex: o bloco aparece no card enquanto é digitado.
    """
    parts = []
    pos = 0
    for m in FENCE_RE.finditer(md or ""):
        before = md[pos:m.start()].strip()
        if before:
            parts.append(("text", before, ""))
        lang = (m.group(1) or "").strip().split()[0] if m.group(1).strip() else ""
        parts.append(("code", m.group(2).rstrip(), lang))
        pos = m.end()
    tail = (md or "")[pos:].strip()
    if tail:
        parts.append(("text", tail, ""))
    return parts or [("text", "", "")]


def md_inline_to_html(text: str) -> str:
    """Converte um subconjunto de Markdown para o rich text do QLabel."""
    out = html.escape(text)
    out = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", out)
    out = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"<i>\1</i>", out)
    out = re.sub(
        r"`([^`]+)`",
        rf'<code style="background:{Color.CODE_BG};color:{Color.CODE_INLINE};'
        r'font-family:Consolas,monospace">\1</code>',
        out,
    )
    lines = []
    for ln in out.split("\n"):
        m = re.match(r"^(#{1,3})\s+(.*)$", ln)
        if m:
            size = {1: 17, 2: 15, 3: 14}[len(m.group(1))]
            lines.append(f'<div style="font-size:{size}px;font-weight:700;'
                         f'margin:4px 0">{m.group(2)}</div>')
        elif re.match(r"^\s*[-*]\s+", ln):
            lines.append("&nbsp;&nbsp;•&nbsp;" + re.sub(r"^\s*[-*]\s+", "", ln))
        else:
            lines.append(ln)
    return "<br>".join(lines)


def _descartar(widget):
    """Tira o widget da tela já, e apaga quando o Qt puder.

    `deleteLater()` sozinho não basta: a decisão do Agente roda num QEventLoop
    aninhado, e a exclusão adiada só acontece quando o loop de fora volta. Até
    lá o "Recebendo resposta…" ficava visível por baixo da resposta final.
    """
    if widget is not None:
        widget.hide()
        widget.deleteLater()


def body_label(objname: str) -> QLabel:
    lb = QLabel()
    lb.setObjectName(objname)
    lb.setTextFormat(Qt.TextFormat.RichText)
    lb.setWordWrap(True)
    lb.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    lb.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
    return lb


class CodeCard(QFrame):
    """Bloco de código com linguagem no cabeçalho e botão de copiar."""

    MAX_HEIGHT = 420

    def __init__(self, code: str, language: str, parent=None):
        super().__init__(parent)
        self.code = code
        self.setObjectName("codeCard")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        header = QFrame()
        header.setObjectName("codeHeader")
        h = QHBoxLayout(header)
        h.setContentsMargins(10, 5, 6, 5)
        lang = QLabel((language or "code").upper())
        lang.setObjectName("codeLang")
        h.addWidget(lang)
        h.addStretch(1)

        self.copy_btn = QToolButton()
        self.copy_btn.setObjectName("codeAction")
        self.copy_btn.setText("Copiar")
        self.copy_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.copy_btn.clicked.connect(self._copy)
        h.addWidget(self.copy_btn)
        outer.addWidget(header)

        self.body = QPlainTextEdit()
        self.body.setObjectName("codeBody")
        self.body.setReadOnly(True)
        self.body.setPlainText(code)
        self.body.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.body.setFrameShape(QFrame.Shape.NoFrame)
        outer.addWidget(self.body)
        self._fit()

    def _fit(self):
        """Altura do card = altura do texto (até um teto, aí rola por dentro)."""
        doc = self.body.document()
        doc.setTextWidth(self.body.viewport().width())
        lines = max(1, self.code.count("\n") + 1)
        h = int(lines * self.body.fontMetrics().lineSpacing() + 18)
        self.body.setFixedHeight(min(h, self.MAX_HEIGHT))

    def _copy(self):
        QGuiApplication.clipboard().setText(self.code)
        self.copy_btn.setText("Copiado ✓")
        QTimer.singleShot(1200, lambda: self.copy_btn.setText("Copiar"))


class CommandCard(QFrame):
    """Comando do agente rodando no shell, com saída ao vivo e botão Parar.

    Cabeçalho: `$ comando` + status (`● rodando 12s` ou `⏸ silêncio 130s`) +
    `▼/▲` para colapsar a saída + `Parar comando`. Corpo: saída ao vivo com
    auto-scroll só quando o usuário estava no fim. Ao terminar, mostra o
    resultado no cabeçalho (`✓ saiu 0 em 3s · 47 linhas`) e colapsa sozinho
    quando a saída é grande — o chat não vira um paredão.
    """

    parar_clicked = pyqtSignal()

    LIMITE_SILENCIO_PADRAO = 120.0

    def __init__(self, comando: str, limite_silencio=None, parent=None):
        super().__init__(parent)
        self.setObjectName("codeCard")
        self.comando = comando
        self._limite_silencio = (limite_silencio
                                 if limite_silencio is not None
                                 else self.LIMITE_SILENCIO_PADRAO)
        self._inicio = time.monotonic()
        self._ultima_saida_em = self._inicio
        self._seguir_fim = True
        self._concluido = False
        self._resumo_curto = ""
        self._fundo = None  # número do processo em segundo plano (ADR-025)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        header = QFrame()
        header.setObjectName("codeHeader")
        h = QHBoxLayout(header)
        h.setContentsMargins(10, 5, 6, 5)
        h.setSpacing(8)

        self.lbl_cmd = QLabel(f"$ {self._linha_curta()}")
        self.lbl_cmd.setObjectName("codeLang")
        self.lbl_cmd.setToolTip(comando)
        self.lbl_cmd.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse)
        self.lbl_cmd.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        h.addWidget(self.lbl_cmd, 1)

        self.lbl_status = QLabel()
        self.lbl_status.setObjectName("commandStatus")
        h.addWidget(self.lbl_status)

        self.btn_toggle = QToolButton()
        self.btn_toggle.setObjectName("codeAction")
        self.btn_toggle.setText("▲ saída")
        self.btn_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_toggle.clicked.connect(self._alternar)
        h.addWidget(self.btn_toggle)

        self.btn_parar = QToolButton()
        self.btn_parar.setObjectName("codeAction")
        self.btn_parar.setText("Parar comando")
        self.btn_parar.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_parar.setToolTip(
            "Encerra este comando e tudo o que ele abriu (equivalente a taskkill /T)")
        self.btn_parar.clicked.connect(lambda: self.parar_clicked.emit())
        h.addWidget(self.btn_parar)

        outer.addWidget(header)

        self.body = QPlainTextEdit()
        self.body.setObjectName("codeBody")
        self.body.setReadOnly(True)
        self.body.setMaximumBlockCount(2000)
        self.body.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.body.setFrameShape(QFrame.Shape.NoFrame)
        self.body.setMinimumHeight(80)
        self.body.setMaximumHeight(260)
        self.body.setPlaceholderText(
            "(sem saída ainda — o comando pode estar iniciando)")
        outer.addWidget(self.body)

        self._atualizar_status(0.0, 0.0)

    # ---------------- helpers ----------------

    def _linha_curta(self) -> str:
        linhas = (self.comando or "").strip().splitlines()
        primeira = linhas[0].strip() if linhas else ""
        return primeira[:80] + ("…" if len(primeira) > 80 else "")

    def _aplicar_tom(self, tom: str):
        cores = {
            "rodando": getattr(Color, "ACCENT", "#7c3aed"),
            "aviso": getattr(Color, "SEARCH", "#e0a800"),
            "ok": TONE.get("success", getattr(Color, "TEXT", "#0a0")),
            "erro": TONE.get("danger", getattr(Color, "TEXT", "#a00")),
        }
        cor = cores.get(tom, getattr(Color, "TEXT_DIM", "#888"))
        self.lbl_status.setStyleSheet(
            f"color:{cor};font-size:11px;font-weight:600;")

    # ---------------- atualização em vida ----------------

    def receber(self, texto: str, seg_silencio: float):
        """Recebe um pedaço de saída (`texto`) ou só um aviso de silêncio.

        Chamado pelo `window.py` via sinal do worker — sempre na thread da GUI.
        """
        if self._concluido:
            return
        if texto:
            self.anexar(texto)

    def anexar(self, texto: str):
        if not texto or self._concluido:
            return
        barra = self.body.verticalScrollBar()
        colado = barra.value() >= barra.maximum() - 8
        self.body.moveCursor(QTextCursor.MoveOperation.End)
        self.body.insertPlainText(texto)
        if colado or self._seguir_fim:
            barra.setValue(barra.maximum())
        self._ultima_saida_em = time.monotonic()

    def tick(self):
        """Chamado por QTimer a cada segundo; mantém o cabeçalho atualizado."""
        if self._concluido or self._fundo is not None:
            return
        agora = time.monotonic()
        self._atualizar_status(agora - self._inicio, agora - self._ultima_saida_em)

    def _atualizar_status(self, seg_total: float, seg_desde_saida: float):
        t = (f"{int(seg_total) // 60}m {int(seg_total) % 60:02d}s"
             if seg_total >= 60 else f"{int(seg_total)}s")
        if seg_desde_saida >= self._limite_silencio:
            self.lbl_status.setText(
                f"⏸ silêncio {int(seg_desde_saida)}s · {t}")
            self._aplicar_tom("aviso")
        else:
            self.lbl_status.setText(f"● rodando {t}")
            self._aplicar_tom("rodando")

    def _alternar(self):
        visivel = self.body.isVisible()
        self.body.setVisible(not visivel)
        self.btn_toggle.setText("▲ saída" if not visivel else "▼ expandir")

    # ---------------- conclusão ----------------

    def concluir(self, saida):
        """Marca o card como terminado. Não chama a UI de novo depois disso."""
        self._concluido = True
        self.btn_parar.setEnabled(False)
        self.btn_parar.hide()
        n_linhas = saida.texto.count("\n") + 1 if saida.texto else 0
        seg = int(saida.segundos)
        t = f"{seg // 60}m {seg % 60:02d}s" if seg >= 60 else f"{seg}s"
        if saida.motivo == "timeout":
            icone, tom = "✗", "erro"
            rotulo = f"tempo esgotado após {t} · {n_linhas} linha(s)"
        elif saida.motivo == "interrompido":
            icone, tom = "■", "aviso"
            rotulo = f"interrompido por você em {t} · {n_linhas} linha(s)"
        elif saida.motivo == "erro":
            icone, tom = "✗", "erro"
            rotulo = f"erro · {n_linhas} linha(s)"
        elif saida.codigo == 0:
            icone, tom = "✓", "ok"
            rotulo = f"saiu 0 em {t} · {n_linhas} linha(s)"
        else:
            icone, tom = "⚠", "aviso"
            rotulo = f"saiu {saida.codigo} em {t} · {n_linhas} linha(s)"
        self.lbl_status.setText(f"{icone} {rotulo}")
        self._aplicar_tom(tom)
        self._resumo_curto = f"$ {self._linha_curta()} — {rotulo}"
        # Saída longa começa colapsada; curta fica aberta.
        if n_linhas > 15 and self.body.isVisible():
            self.body.setVisible(False)
            self.btn_toggle.setText("▼ expandir")

    def resumo_curto(self) -> str:
        return self._resumo_curto or f"$ {self._linha_curta()}"

    # ---------------- segundo plano (ADR-025) ----------------

    def marcar_segundo_plano(self, numero: int):
        """O comando virou processo em segundo plano: segue recebendo saída."""
        self._fundo = numero
        self.lbl_status.setText(f"▶ em segundo plano · processo {numero}")
        self._aplicar_tom("ok")
        self.btn_parar.setText("Parar processo")
        self.btn_parar.setToolTip(f"Encerra o processo {numero} e tudo o que ele abriu")
        self._resumo_curto = (f"$ {self._linha_curta()} — em segundo plano "
                              f"(processo {numero})")

    def fim_segundo_plano(self, codigo):
        """O processo em segundo plano terminou (sozinho ou parado)."""
        if self._concluido:
            return
        self._concluido = True
        self.btn_parar.setEnabled(False)
        self.btn_parar.hide()
        self.lbl_status.setText(f"■ processo {self._fundo} encerrado (código {codigo})")
        self._aplicar_tom("aviso")
        self._resumo_curto = (f"$ {self._linha_curta()} — processo {self._fundo} "
                              f"encerrado (código {codigo})")


class UserMessage(QFrame):
    """Bolha do usuário, alinhada à direita."""

    def __init__(self, text: str, parent=None):
        super().__init__(parent)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 6, 0, 6)
        row.addStretch(1)

        bubble = QFrame()
        bubble.setObjectName("userBubble")
        bubble.setMaximumWidth(640)
        inner = QVBoxLayout(bubble)
        inner.setContentsMargins(12, 9, 12, 9)
        label = body_label("userText")
        label.setText(md_inline_to_html(text))
        inner.addWidget(label)
        row.addWidget(bubble)


class AgentMessage(QFrame):
    """Resposta do DeepSeek: texto fluido + cards de código, à esquerda."""

    def __init__(self, parent=None):
        super().__init__(parent)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 6, 0, 6)
        row.setSpacing(8)

        glyph = QLabel("◆")
        glyph.setObjectName("agentGlyph")
        glyph.setAlignment(Qt.AlignmentFlag.AlignCenter)
        glyph.setFixedSize(22, 22)
        row.addWidget(glyph, 0, Qt.AlignmentFlag.AlignTop)

        holder = QWidget()
        self.stack = QVBoxLayout(holder)
        self.stack.setContentsMargins(0, 0, 0, 0)
        self.stack.setSpacing(8)
        row.addWidget(holder, 1)

        self._raw = ""
        self.set_content("…")

    def set_content(self, md: str):
        """Substitui o conteúdo. Chamado a cada chunk durante o streaming."""
        if md == self._raw:
            return
        self._raw = md
        self._clear_content()
        for kind, content, lang in split_markdown(md):
            if kind == "code":
                self.stack.addWidget(CodeCard(content, lang))
            elif content:
                label = body_label("agentText")
                label.setText(md_inline_to_html(content))
                self.stack.addWidget(label)

    def set_markdown_content(self, md: str, resposta, on_decision=None,
                             show_decisions=True):
        texto = md or ""
        if resposta and resposta.valida:
            for acao in resposta.acoes:
                if acao.verbo == "decidir" and acao.bruto:
                    texto = texto.replace(acao.bruto, "", 1)
        self.set_content(texto)
        if show_decisions and resposta and resposta.valida and on_decision:
            for acao in resposta.acoes:
                if acao.verbo == "decidir":
                    self.stack.addWidget(DecisionCard(acao, on_decision))

    def set_structured_content(self, resposta, on_decision=None,
                               show_decisions=True):
        """Mostra campos da resposta API como texto e cards, nunca JSON cru."""
        if not resposta.valida:
            self.set_content(
                "Resposta estruturada inválida; o conteúdo não foi exibido.")
            return
        self._raw = ""
        self._clear_content()
        if resposta.resumo.strip():
            label = body_label("agentText")
            label.setText(md_inline_to_html(resposta.resumo))
            self.stack.addWidget(label)
        for acao in resposta.acoes:
            if acao.verbo in ("criar", "modificar") and acao.conteudo is not None:
                linguagem = PurePosixPath(acao.caminho or "").suffix.lstrip(".")
                self.stack.addWidget(CodeCard(acao.conteudo, linguagem))
            elif acao.verbo == "rodar" and acao.conteudo:
                self.stack.addWidget(CodeCard(acao.conteudo, "shell"))
            elif (acao.verbo == "decidir" and show_decisions
                  and on_decision):
                self.stack.addWidget(DecisionCard(acao, on_decision))

    def _clear_content(self):
        while self.stack.count():
            _descartar(self.stack.takeAt(0).widget())


class DecisionTextEdit(QPlainTextEdit):
    """Caixa de texto para respostas livres, alinhada ao composer do app.

    Enter confirma, Shift+Enter quebra linha, Esc cancela. Colar imagem (ou
    arquivo do Explorer) anexa à resposta em vez de virar texto.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setPlaceholderText(
            "Descreva sua decisão…   Enter confirma · Shift+Enter quebra "
            "linha · Ctrl+V cola imagem")
        self.setMinimumHeight(82)
        self.setMaximumHeight(140)
        self.setTabChangesFocus(True)

    def _card(self):
        pai = self.parent()
        while pai is not None and not isinstance(pai, DecisionCard):
            pai = pai.parent()
        return pai

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if not (event.modifiers() & Qt.KeyboardModifier.ShiftModifier):
                card = self._card()
                if card is not None:
                    card._submit_other()
                    return
        if event.key() == Qt.Key.Key_Escape:
            card = self._card()
            if card is not None:
                card._cancel_other()
                return
        super().keyPressEvent(event)

    def canInsertFromMimeData(self, source):
        if source.hasImage() or source.hasUrls():
            return True
        return super().canInsertFromMimeData(source)

    def insertFromMimeData(self, source):
        card = self._card()
        if card is not None:
            if source.hasImage():
                imagem = source.imageData()
                if imagem is not None:
                    card._anexar_imagem(imagem)
                    return
            if source.hasUrls():
                caminhos = [u.toLocalFile() for u in source.urls()
                            if u.isLocalFile() and u.toLocalFile()]
                if caminhos:
                    card._anexar_arquivos(caminhos)
                    return
        super().insertFromMimeData(source)


class BotaoOpcao(QToolButton):
    """Opção de decisão: texto à esquerda e com quebra de linha.

    `QToolButton` centraliza o texto e ignora `text-align` do QSS; aqui o
    fundo/borda continuam vindo do tema e só o texto é desenhado à parte.
    """

    PAD_X, PAD_Y = 13, 10

    def __init__(self, parent=None):
        super().__init__(parent)
        politica = QSizePolicy(QSizePolicy.Policy.Expanding,
                               QSizePolicy.Policy.Minimum)
        politica.setHeightForWidth(True)
        self.setSizePolicy(politica)

    def _altura_texto(self, largura: int) -> int:
        util = max(40, largura - 2 * self.PAD_X)
        caixa = self.fontMetrics().boundingRect(
            0, 0, util, 10_000, int(Qt.TextFlag.TextWordWrap), self.text())
        return caixa.height()

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, largura):
        return self._altura_texto(largura) + 2 * self.PAD_Y + 4

    def sizeHint(self):
        # Não depende da largura atual: isso realimentaria o layout sem fim.
        # A altura real vem de `heightForWidth` na largura que o layout der.
        largura = min(560, self.fontMetrics().horizontalAdvance(self.text())
                      + 2 * self.PAD_X)
        return QSize(largura, self.heightForWidth(largura))

    def minimumSizeHint(self):
        return QSize(120, self.fontMetrics().height() + 2 * self.PAD_Y)

    def paintEvent(self, _event):
        opcao = QStyleOptionToolButton()
        self.initStyleOption(opcao)
        texto = opcao.text
        opcao.text = ""
        pintor = QStylePainter(self)
        pintor.drawComplexControl(QStyle.ComplexControl.CC_ToolButton, opcao)
        grupo = (QPalette.ColorGroup.Active if self.isEnabled()
                 else QPalette.ColorGroup.Disabled)
        pintor.setPen(opcao.palette.color(grupo, QPalette.ColorRole.ButtonText))
        area = self.rect().adjusted(self.PAD_X, self.PAD_Y - 2,
                                    -self.PAD_X, -(self.PAD_Y - 2))
        pintor.drawText(area, int(Qt.AlignmentFlag.AlignLeft
                                  | Qt.AlignmentFlag.AlignVCenter
                                  | Qt.TextFlag.TextWordWrap), texto)


def _repolir(widget):
    """Reaplica o QSS depois de mudar uma propriedade dinâmica."""
    for w in [widget, *widget.findChildren(QWidget)]:
        w.style().unpolish(w)
        w.style().polish(w)


class DecisionCard(QFrame):
    """Apresenta uma pergunta pendente e entrega ao app a escolha do usuário.

    Âmbar marca a opção que o DeepSeek recomenda; verde marca a que você
    escolheu. Depois de resolvido, o card continua no chat como registro:
    qual foi a escolha e se ela seguiu ou divergiu da recomendação.

    `on_choose(acao, escolha)` — ou `on_choose(acao, escolha, anexos)` quando
    a resposta livre leva imagem/arquivo (lista de `anexos.Anexo`).
    """

    def __init__(self, acao, on_choose, parent=None):
        super().__init__(parent)
        self.setObjectName("decisionCard")
        self.setProperty("estado", "pendente")
        self.acao = acao
        self.on_choose = on_choose
        self.settled = False
        self.escolha = None
        self.anexos = []
        self.opcoes = list(acao.extras.get("opcoes") or [])
        recomendada = acao.extras.get("recomendada")
        self.recomendada = (recomendada if isinstance(recomendada, int)
                            and 1 <= recomendada <= len(self.opcoes) else None)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(8)

        heading = QLabel("DECISÃO NECESSÁRIA")
        heading.setObjectName("decisionTitle")
        heading.setWordWrap(True)
        layout.addWidget(heading)
        question = QLabel(acao.extras["pergunta"])
        question.setObjectName("decisionQuestion")
        question.setWordWrap(True)
        question.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(question)

        if self.recomendada:
            motivo = acao.extras.get("motivo")
            recomendacao = QLabel(
                f"★ <b>Recomendação do DeepSeek:</b> opção {self.recomendada}"
                + (f" — {html.escape(motivo)}" if motivo else ""))
            recomendacao.setObjectName("decisionRecommendation")
            recomendacao.setTextFormat(Qt.TextFormat.RichText)
            recomendacao.setWordWrap(True)
            layout.addWidget(recomendacao)

        self.botoes = []
        for indice, opcao in enumerate(self.opcoes, start=1):
            button = BotaoOpcao()
            button.setObjectName("decisionOption")
            if indice == self.recomendada:
                button.setText(f"{indice}. {opcao}   ★ recomendada")
                button.setProperty("recomendada", True)
                button.setToolTip("Opção recomendada pelo DeepSeek")
            else:
                button.setText(f"{indice}. {opcao}")
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(
                lambda _checked=False, escolha=opcao: self._choose(escolha))
            layout.addWidget(button)
            self.botoes.append(button)

        self.other = QToolButton()
        self.other.setObjectName("decisionOther")
        self.other.setText("✎  Outra resposta…")
        self.other.setCursor(Qt.CursorShape.PointingHandCursor)
        self.other.clicked.connect(self._other)
        layout.addWidget(self.other, 0, Qt.AlignmentFlag.AlignLeft)

        # Área de resposta livre: texto + anexos + Cancelar/Confirmar.
        self.other_area = QWidget(self)
        area = QVBoxLayout(self.other_area)
        area.setContentsMargins(0, 2, 0, 0)
        area.setSpacing(6)
        self.other_input = DecisionTextEdit(self.other_area)
        self.other_input.setObjectName("decisionInput")
        area.addWidget(self.other_input)

        self.barra_anexos = QWidget(self.other_area)
        self.lay_anexos = QHBoxLayout(self.barra_anexos)
        self.lay_anexos.setContentsMargins(0, 0, 0, 0)
        self.lay_anexos.setSpacing(6)
        self.lay_anexos.addStretch(1)
        self.barra_anexos.hide()
        area.addWidget(self.barra_anexos)

        acoes = QHBoxLayout()
        acoes.setContentsMargins(0, 0, 0, 0)
        acoes.setSpacing(8)
        self.attach_other = QToolButton()
        self.attach_other.setObjectName("decisionAttach")
        self.attach_other.setText("🖼  Anexar imagem")
        self.attach_other.setToolTip(
            "Envia imagem ou arquivo junto da sua resposta (Ctrl+V também cola)")
        self.attach_other.setCursor(Qt.CursorShape.PointingHandCursor)
        self.attach_other.clicked.connect(self._escolher_anexo)
        acoes.addWidget(self.attach_other)
        acoes.addStretch(1)
        self.cancel_other = QPushButton("Cancelar")
        self.cancel_other.setObjectName("decisionCancel")
        self.cancel_other.setCursor(Qt.CursorShape.PointingHandCursor)
        self.cancel_other.setToolTip("Fecha a resposta livre e volta às opções (Esc)")
        self.cancel_other.clicked.connect(self._cancel_other)
        acoes.addWidget(self.cancel_other)
        self.confirm_other = QPushButton("Confirmar")
        self.confirm_other.setObjectName("decisionConfirm")
        self.confirm_other.setCursor(Qt.CursorShape.PointingHandCursor)
        self.confirm_other.clicked.connect(self._submit_other)
        acoes.addWidget(self.confirm_other)
        area.addLayout(acoes)
        self.other_area.setVisible(False)
        layout.addWidget(self.other_area)

        # Registro do que foi decidido (aparece ao resolver).
        self.lbl_escolha = QLabel()
        self.lbl_escolha.setObjectName("decisionChosen")
        self.lbl_escolha.setTextFormat(Qt.TextFormat.RichText)
        self.lbl_escolha.setWordWrap(True)
        self.lbl_escolha.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse)
        self.lbl_escolha.hide()
        layout.addWidget(self.lbl_escolha)
        self.lbl_veredito = QLabel()
        self.lbl_veredito.setObjectName("decisionVerdict")
        self.lbl_veredito.hide()
        layout.addWidget(self.lbl_veredito)

    # ---------------- resposta livre ----------------

    def _other(self):
        self.other_area.setVisible(True)
        self.other.setVisible(False)
        self.other_input.setFocus()

    def _cancel_other(self):
        """Fecha a resposta livre sem registrar nada; as opções continuam."""
        if self.settled:
            return
        self.other_input.clear()
        self._limpar_anexos(descartar=True)
        self.other_area.setVisible(False)
        self.other.setVisible(True)

    def _submit_other(self):
        if self.settled:
            return
        resposta = self.other_input.toPlainText().strip()
        if not resposta and self.anexos:
            resposta = "Veja o anexo enviado."
        if resposta:
            self.other_input.clear()
            anexos_resposta = list(self.anexos)
            self._limpar_anexos(descartar=False)
            self._choose(resposta, anexos_resposta)

    def _escolher_anexo(self):
        caminhos, _ = QFileDialog.getOpenFileNames(
            self, "Anexar à resposta", "",
            "Imagens (*.png *.jpg *.jpeg *.gif *.webp *.bmp);;Todos os arquivos (*)")
        if caminhos:
            self._anexar_arquivos(caminhos)

    def _anexar_imagem(self, imagem):
        anexo = anexos.de_imagem(imagem)
        if anexo:
            self._adicionar_anexo(anexo)

    def _anexar_arquivos(self, caminhos):
        for caminho in caminhos:
            anexo = anexos.de_arquivo(caminho)
            if anexo:
                self._adicionar_anexo(anexo)

    def _adicionar_anexo(self, anexo):
        if self.settled:
            anexo.descartar()
            return
        self.anexos.append(anexo)
        chip = QFrame()
        chip.setObjectName("chipAnexo")
        chip.anexo = anexo
        lay = QHBoxLayout(chip)
        lay.setContentsMargins(9, 2, 3, 2)
        lay.setSpacing(4)
        rotulo = QLabel(f"{anexo.icone} {anexo.rotulo}")
        rotulo.setObjectName("chipTexto")
        rotulo.setToolTip(anexo.caminho or anexo.rotulo)
        lay.addWidget(rotulo)
        fechar = QToolButton()
        fechar.setObjectName("chipFechar")
        fechar.setText("✕")
        fechar.setCursor(Qt.CursorShape.PointingHandCursor)
        fechar.clicked.connect(lambda: self._remover_anexo(chip))
        lay.addWidget(fechar)
        self.lay_anexos.insertWidget(self.lay_anexos.count() - 1, chip)
        self.barra_anexos.show()
        self.other_input.setFocus()

    def _remover_anexo(self, chip):
        if chip.anexo in self.anexos:
            self.anexos.remove(chip.anexo)
        chip.anexo.descartar()
        _descartar(chip)
        if not self.anexos:
            self.barra_anexos.hide()

    def _limpar_anexos(self, descartar: bool):
        for i in reversed(range(self.lay_anexos.count())):
            w = self.lay_anexos.itemAt(i).widget()
            if w is not None:
                self.lay_anexos.removeWidget(w)
                _descartar(w)
        if descartar:
            for anexo in self.anexos:
                anexo.descartar()
        self.anexos = []
        self.barra_anexos.hide()

    # ---------------- resolução ----------------

    def _travar(self):
        for button in self.findChildren(QToolButton):
            button.setEnabled(False)
        self.confirm_other.setEnabled(False)
        self.cancel_other.setEnabled(False)
        self.other_input.setEnabled(False)
        self.other_area.setVisible(False)
        self.other.setVisible(False)

    def _marcar_resolvido(self, escolha: str, origem: str | None, anexos=None):
        self.settled = True
        self.escolha = escolha
        self._travar()
        livre = escolha not in self.opcoes
        for button, opcao in zip(self.botoes, self.opcoes):
            if opcao == escolha:
                button.setProperty("escolhida", True)
                button.setText(f"✓ {button.text()}")
        rotulo = "resposta livre" if livre else escolha
        titulo = self.findChild(QLabel, "decisionTitle")
        if titulo is not None:
            titulo.setText(
                f"✓ DECISÃO REGISTRADA ({origem}): {rotulo}" if origem
                else f"✓ DECISÃO REGISTRADA: {rotulo}")
        detalhe = f"<b>Sua escolha:</b> {html.escape(escolha)}"
        if anexos:
            detalhe += (f"<br>📎 {len(anexos)} anexo(s): "
                        + html.escape(", ".join(a.rotulo for a in anexos)))
        if origem:
            detalhe += (f"<br><span style='color:{Color.TEXT_DIM}'>"
                        f"respondido pelo {html.escape(origem)}</span>")
        self.lbl_escolha.setText(detalhe)
        self.lbl_escolha.show()
        if self.recomendada:
            recomendada = self.opcoes[self.recomendada - 1]
            if escolha == recomendada:
                self.lbl_veredito.setText("★ Seguiu a recomendação do DeepSeek")
                self.lbl_veredito.setProperty("tom", "segue")
            else:
                self.lbl_veredito.setText(
                    "↯ Diferente da recomendação do DeepSeek "
                    f"(opção {self.recomendada})")
                self.lbl_veredito.setProperty("tom", "diverge")
            self.lbl_veredito.show()
        self.setProperty("estado", "resolvida")
        _repolir(self)

    def _choose(self, escolha: str, anexos_resposta=None):
        if self.settled:
            return
        anexos_resposta = list(anexos_resposta or [])
        self._marcar_resolvido(escolha, None, anexos_resposta)
        if anexos_resposta:
            self.on_choose(self.acao, escolha, anexos_resposta)
        else:
            self.on_choose(self.acao, escolha)

    def marcar_respondido_externo(self, origem: str, escolha: str, anexos=None):
        """Resolve o card sem chamar `on_choose` (quem respondeu foi o painel).

        Usado quando o celular responde pelo mesmo `QEventLoop` do agente: o
        agente já destravou, mas o card local precisa parar de pedir resposta.
        """
        if self.settled:
            return
        self._limpar_anexos(descartar=True)
        self._marcar_resolvido(escolha, origem, anexos)

    def cancel(self):
        if self.settled:
            return
        self.settled = True
        self._limpar_anexos(descartar=True)
        self._travar()
        self.findChild(QLabel, "decisionTitle").setText("DECISÃO CANCELADA")
        self.setProperty("estado", "cancelada")
        _repolir(self)


class DecisionInputDialog(QDialog):
    """Solicita uma escolha personalizada usando o tema da janela principal."""

    def __init__(self, pergunta: str, parent=None):
        super().__init__(parent)
        self.setObjectName("decisionDialog")
        self.setWindowTitle("Outra resposta")
        self.setMinimumWidth(420)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 16)
        layout.setSpacing(12)

        heading = QLabel("SUA DECISÃO")
        heading.setObjectName("decisionDialogTitle")
        layout.addWidget(heading)

        question = QLabel(pergunta)
        question.setObjectName("decisionDialogQuestion")
        question.setWordWrap(True)
        layout.addWidget(question)

        self.input = QLineEdit()
        self.input.setObjectName("decisionInput")
        self.input.setPlaceholderText("Descreva sua decisão…")
        self.input.setClearButtonEnabled(True)
        self.input.setAccessibleName("Sua decisão")
        layout.addWidget(self.input)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel)
        confirm = buttons.button(QDialogButtonBox.StandardButton.Ok)
        confirm.setText("Confirmar")
        confirm.setObjectName("decisionConfirm")
        cancel = buttons.button(QDialogButtonBox.StandardButton.Cancel)
        cancel.setText("Cancelar")
        cancel.setObjectName("decisionCancel")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)


class ActionCard(QFrame):
    """Resumo do que o modelo quer fazer no disco, com o botão que abre a revisão.

    Fica no chat, embaixo da resposta. Enquanto não for clicado, nada mudou no
    projeto — `preparar()` só leu.
    """

    def __init__(self, planos, on_revisar, parent=None):
        super().__init__(parent)
        self.setObjectName("actionCard")
        self.planos = planos

        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(6)

        aplicaveis = [p for p in planos if p.aplicavel]
        recusados = [p for p in planos if p.erro]
        alertas = [p for p in aplicaveis if p.avisos]

        titulo = QLabel(f"◆ {len(aplicaveis)} alteração(ões) propostas")
        titulo.setObjectName("actionTitle")
        lay.addWidget(titulo)

        for plano in planos[:8]:
            marca = "✗" if plano.erro else ("·" if plano.sem_efeito else
                                            ("⚠" if plano.avisos else "▸"))
            linha = QLabel(f"{marca}  {plano.rotulo if not plano.erro else plano.rel}")
            linha.setObjectName("actionLine")
            if plano.erro:
                linha.setToolTip(plano.erro)
            elif plano.avisos:
                linha.setToolTip("\n".join(plano.avisos))
            lay.addWidget(linha)
        if len(planos) > 8:
            mais = QLabel(f"… e mais {len(planos) - 8}")
            mais.setObjectName("actionLine")
            lay.addWidget(mais)

        rodape = QHBoxLayout()
        recado = []
        if recusados:
            recado.append(f"{len(recusados)} recusado(s) pelo sandbox")
        if alertas:
            recado.append(f"{len(alertas)} com aviso")
        if recado:
            aviso = QLabel(" · ".join(recado))
            aviso.setObjectName("actionWarn")
            rodape.addWidget(aviso)
        rodape.addStretch(1)

        self.btn = QToolButton()
        self.btn.setObjectName("actionApply")
        self.btn.setText("Revisar e aplicar")
        self.btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn.setEnabled(bool(aplicaveis))
        self.btn.clicked.connect(lambda: on_revisar(self))
        rodape.addWidget(self.btn)
        lay.addLayout(rodape)

    def selar(self, texto: str):
        """Depois de aplicado, o card vira registro do que aconteceu.

        Tolera o widget já destruído: o card pode ter sumido (conversa trocada,
        histórico recarregado) enquanto a aplicação rodava em thread.
        """
        try:
            self.btn.setEnabled(False)
            self.btn.setText(texto)
        except RuntimeError:
            pass


class _ConteudoRolavel(QWidget):
    """Conteúdo do chat que informa ao QScrollArea a altura REAL.

    O QScrollArea dimensiona o conteúdo pelo `minimumSizeHint`, e texto com
    quebra de linha declara um mínimo medido numa largura menor que a da tela:
    cada resposta sobrava ~70px. Somado na conversa, virava uma área vazia no
    fim, e rolar até o fim mostrava só fundo.
    """

    def minimumSizeHint(self):
        base = super().minimumSizeHint()
        layout = self.layout()
        if layout is not None and layout.hasHeightForWidth() and self.width() > 0:
            return QSize(base.width(), layout.totalHeightForWidth(self.width()))
        return base


class ChatPanel(QScrollArea):
    """Lista rolável de mensagens, numa coluna central de largura limitada.

    Rolagem: a barra acompanha a resposta enquanto você está no fim. Subir
    (roda do mouse, arrastar a barra, teclado) solta; nada te puxa de volta.
    Descer até o fim, ou o botão flutuante "Ir para o fim", religa.

    `historico` é a lista de mensagens em memória (`role`, `content`, `ts`),
    pronta para o painel remoto. `streaming` é o parcial em curso (ou None).
    Guarda o texto **amigável** — nunca o envelope JSON/XML cru.
    """

    LARGURA_MAX = 880
    MARGEM_LADO = 18
    # Distância do fim (px) que ainda conta como "estou no fim".
    FOLGA_FIM = 48

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self._holder = _ConteudoRolavel()
        self._holder.setObjectName("root")

        # Coluna central com largura máxima: em tela larga, texto de ponta a
        # ponta fica ilegível — o olho perde a linha na volta.
        fora = QHBoxLayout(self._holder)
        fora.setContentsMargins(self.MARGEM_LADO, 12, self.MARGEM_LADO, 12)
        fora.addStretch(1)

        # Largura FIXA, recalculada no resize. Com largura só máxima o Qt media
        # a altura dos textos quebrados numa coluna mais estreita que a real, e
        # a diferença virava uma área vazia no fim da conversa.
        self._coluna = QWidget()
        self._lay = QVBoxLayout(self._coluna)
        self._lay.setContentsMargins(0, 0, 0, 0)
        self._lay.setSpacing(2)
        self._lay.addStretch(1)
        fora.addWidget(self._coluna)
        fora.addStretch(1)
        self.setWidget(self._holder)
        self._ajustar_coluna()

        self._pending = None  # AgentMessage em streaming
        self._seguir_fim = True
        self._ultimo_valor = 0   # posição anterior, para saber se desceu
        self._max_anterior = 0
        self._novidade = False   # chegou conteúdo enquanto você lia lá em cima

        # Botão flutuante sobre o viewport (não rola junto com o conteúdo).
        self.btn_fim = QToolButton(self.viewport())
        self.btn_fim.setObjectName("scrollToEnd")
        self.btn_fim.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_fim.setToolTip("Ir para o fim da conversa e voltar a acompanhar")
        self.btn_fim.clicked.connect(self.ir_para_o_fim)
        self.btn_fim.hide()

        # Estado exposto ao painel remoto.
        self.historico: list[dict] = []
        self.streaming: str | None = None

        bar = self.verticalScrollBar()
        bar.rangeChanged.connect(self._faixa_mudou)
        bar.valueChanged.connect(self._posicao_mudou)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._ajustar_coluna()
        self._posicionar_botao_fim()

    def _ajustar_coluna(self):
        livre = self.viewport().width() - 2 * self.MARGEM_LADO
        self._coluna.setFixedWidth(max(240, min(self.LARGURA_MAX, livre)))

    # ---------------- histórico (painel remoto) ----------------

    def historico_json(self) -> dict:
        """Snapshot para o painel remoto: histórico + streaming atual."""
        return {
            "messages": list(self.historico),
            "streaming": self.streaming,
        }

    def _registrar(self, role: str, content: str):
        self.historico.append({"role": role, "content": content, "ts": _ts()})

    # ---------------- rolagem ----------------

    def _posicao_mudou(self, valor):
        """Movimento da pessoa (roda, barra, teclado, toque). O nosso vem bloqueado.

        Saiu do fim → para de acompanhar. Desceu de volta ao fim → acompanha de
        novo. Valor que só diminuiu porque o conteúdo encolheu (o Qt corta a
        posição no novo máximo) não religa nada.
        """
        bar = self.verticalScrollBar()
        no_fim = valor >= bar.maximum() - self.FOLGA_FIM
        if not no_fim:
            self._seguir_fim = False
        elif valor > self._ultimo_valor:
            self._seguir_fim = True
        self._ultimo_valor = valor
        self._atualizar_botao_fim()

    def _faixa_mudou(self, _minimo, maximo):
        """O conteúdo mudou de altura: acompanha, ou avisa que há novidade."""
        cresceu = maximo > self._max_anterior
        self._max_anterior = maximo
        if self._seguir_fim:
            self._ir_para(maximo)
        elif cresceu:
            self._novidade = True
        self._atualizar_botao_fim()

    def _ir_para(self, valor):
        bar = self.verticalScrollBar()
        bar.blockSignals(True)
        bar.setValue(valor)
        bar.blockSignals(False)
        self._ultimo_valor = bar.value()

    def ir_para_o_fim(self):
        """Vai ao fim e volta a acompanhar o que chegar."""
        self._seguir_fim = True
        self._novidade = False
        self._ir_para(self.verticalScrollBar().maximum())
        self._atualizar_botao_fim()

    def _atualizar_botao_fim(self):
        bar = self.verticalScrollBar()
        longe = bar.maximum() - bar.value() > self.FOLGA_FIM
        if not longe:
            self._novidade = False
        self.btn_fim.setText("↓  Nova resposta" if self._novidade
                             else "↓  Ir para o fim")
        self.btn_fim.setProperty("novidade", self._novidade)
        self.btn_fim.style().unpolish(self.btn_fim)
        self.btn_fim.style().polish(self.btn_fim)
        self.btn_fim.adjustSize()
        self._posicionar_botao_fim()
        self.btn_fim.setVisible(longe)
        if longe:
            self.btn_fim.raise_()

    def _posicionar_botao_fim(self):
        area = self.viewport().rect()
        x = (area.width() - self.btn_fim.width()) // 2
        y = area.height() - self.btn_fim.height() - 14
        self.btn_fim.move(max(0, x), max(0, y))

    def _scroll_bottom(self):
        self.ir_para_o_fim()

    def _insert(self, widget):
        self._lay.insertWidget(self._lay.count() - 1, widget)

    def clear(self):
        while self._lay.count() > 1:
            _descartar(self._lay.takeAt(0).widget())
        self._pending = None
        self._seguir_fim = True
        self._novidade = False
        self.historico = []
        self.streaming = None

    def add_user(self, text: str):
        # Quem acabou de enviar quer ver o que vem: volta a acompanhar o fim.
        self._seguir_fim = True
        self._insert(UserMessage(text))
        self._registrar("user", text)
        QTimer.singleShot(0, self._scroll_bottom)

    def add_command(self, comando: str) -> CommandCard:
        """Cria um card ao vivo para um comando do agente. Retorna o card."""
        self._seguir_fim = True
        card = CommandCard(comando)
        self._insert(card)
        QTimer.singleShot(0, self._scroll_bottom)
        return card

    def registrar_comando(self, resumo: str):
        """Registra no histórico (painel remoto) o resultado de um comando.

        Não cria widget — o card visual já é a fonte do que foi visto na tela.
        """
        self._registrar("system", resumo)

    def start_agent(self) -> AgentMessage:
        self._pending = AgentMessage()
        self._insert(self._pending)
        self.streaming = ""
        return self._pending

    def update_agent(self, md: str):
        if self._pending:
            self._pending.set_content(md)
            self.streaming = md

    def finish_agent(self, md: str, resposta=None, formato="markdown",
                     on_decision=None, show_decisions=True):
        if self._pending:
            if resposta is not None and not resposta.valida:
                self._pending.set_content(
                    resposta.resumo or "Resposta inválida; nenhuma ação foi aplicada.")
                captura = (md or "").strip()
                if captura:
                    legenda = QLabel(
                        f"Conteúdo recebido pelo app ({len(captura):,} caracteres):"
                        .replace(",", "."))
                    legenda.setObjectName("agentText")
                    legenda.setWordWrap(True)
                    self._pending.stack.addWidget(legenda)
                    self._pending.stack.addWidget(CodeCard(captura, formato))
            elif formato == "markdown" and resposta is not None:
                self._pending.set_markdown_content(
                    md, resposta, on_decision, show_decisions)
            elif resposta is not None:
                self._pending.set_structured_content(
                    resposta, on_decision, show_decisions)
            else:
                self._pending.set_content(md or "Sem resposta.")
            self._pending = None
            # Guarda o texto amigável (não o envelope cru). O painel remoto
            # não tem como saber que precisa decodificar JSON/XML.
            self._registrar("assistant",
                            texto_amigavel(md, resposta, formato))
            self.streaming = None

    def add_actions(self, planos, on_revisar):
        card = ActionCard(planos, on_revisar)
        self._insert(card)
        return card

    def add_decision(self, acao, on_choose):
        card = DecisionCard(acao, on_choose)
        self._insert(card)
        return card

    def registrar_decisao(self, acao, escolha, origem="pc", anexos=None):
        """Guarda no histórico a decisão resolvida (ou cancelada).

        O painel remoto desenha `role: "decision"` como card resolvido, com a
        recomendada em âmbar e a escolha em verde — a mesma leitura do PC.
        `escolha=None` registra cancelamento.
        """
        extras = getattr(acao, "extras", {}) or {}
        pergunta = str(extras.get("pergunta") or "")
        rotulos = [a.rotulo for a in (anexos or [])]
        self.historico.append({
            "role": "decision",
            "content": (f"Decisão: {pergunta} → {escolha}" if escolha
                        else f"Decisão cancelada: {pergunta}"),
            "ts": _ts(),
            "decision": {
                "pergunta": pergunta,
                "opcoes": [str(o) for o in (extras.get("opcoes") or [])],
                "recomendada": extras.get("recomendada"),
                "motivo": extras.get("motivo"),
                "escolha": escolha,
                "origem": origem,
                "anexos": rotulos,
            },
        })

    def add_system(self, texto: str):
        """Nota do app (resultado de aplicação, erro de formato).

        Relatório em que tudo deu certo ganha verde: é o retorno mais frequente
        e o que você mais quer conferir de relance.
        """
        linhas = [l for l in (texto or "").splitlines() if l.strip()]
        tudo_ok = bool(linhas) and all(l.lstrip().startswith("✓") for l in linhas)
        lb = QLabel(texto)
        lb.setObjectName("systemOk" if tudo_ok else "systemNote")
        lb.setWordWrap(True)
        self._insert(lb)
        self._registrar("system", texto)
        return lb

    def load_history(self, messages, formato="markdown", on_decision=None):
        """Repõe na tela uma conversa lida do DeepSeek.

        O texto que ficou guardado pela API também pode vir em JSON/XML
        (a conversa foi feita no modo JSON, e a mensagem crua é o envelope).
        `parse` decodifica; o `historico` guarda a versão amigável, não o cru.
        """
        self.clear()
        for m in messages:
            if m.get("role") == "user":
                self.add_user(m.get("content", ""))
            else:
                msg = AgentMessage()
                content = m.get("content", "")
                lido = None
                if formato == "markdown":
                    parsed = parse(content, formato="markdown")
                    if parsed.valida:
                        msg.set_markdown_content(content, parsed, on_decision)
                    else:
                        msg.set_content(parsed.resumo)
                    lido = parsed
                else:
                    outro_formato = "xml" if formato == "json" else "json"
                    parsed = None
                    for protocolo in (formato, outro_formato):
                        resposta = parse(content, formato=protocolo)
                        if resposta.valida:
                            msg.set_structured_content(resposta, on_decision)
                            lido = resposta
                            break
                        parsed = resposta
                    else:
                        msg.set_structured_content(parsed, on_decision)
                        lido = parsed
                self._insert(msg)
                self._registrar(
                    "assistant", texto_amigavel(content, lido, formato))
