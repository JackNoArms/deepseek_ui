"""Painel da fila de envio, acima do composer.

Mostra cada mensagem que espera a vez (texto, anexos, modo) com ✎ para
editar o texto e ✕ para cancelar. Quem decide o que é a fila é o
`MainWindow`; aqui só se desenha a lista que ele passa em `set_itens` e se
avisa quando a pessoa edita ou cancela.
"""

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
)

LIMITE_TEXTO = 140


def _resumo(texto: str) -> str:
    linha = " ".join((texto or "").split())
    return linha if len(linha) <= LIMITE_TEXTO else linha[:LIMITE_TEXTO - 1] + "…"


class EditarFilaDialog(QDialog):
    """Edita o texto de uma mensagem que ainda não saiu da fila."""

    def __init__(self, texto: str, parent=None):
        super().__init__(parent)
        self.setObjectName("decisionDialog")
        self.setWindowTitle("Editar mensagem da fila")
        self.setMinimumWidth(520)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 16, 18, 14)
        lay.setSpacing(10)
        titulo = QLabel("EDITAR MENSAGEM DA FILA")
        titulo.setObjectName("decisionDialogTitle")
        lay.addWidget(titulo)
        self.editor = QPlainTextEdit()
        self.editor.setObjectName("decisionInput")
        self.editor.setPlainText(texto)
        self.editor.setMinimumHeight(140)
        lay.addWidget(self.editor)
        botoes = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel)
        salvar = botoes.button(QDialogButtonBox.StandardButton.Save)
        salvar.setText("Salvar")
        salvar.setObjectName("decisionConfirm")
        cancelar = botoes.button(QDialogButtonBox.StandardButton.Cancel)
        cancelar.setText("Cancelar")
        cancelar.setObjectName("decisionCancel")
        botoes.accepted.connect(self.accept)
        botoes.rejected.connect(self.reject)
        lay.addWidget(botoes)

    def texto(self) -> str:
        return self.editor.toPlainText().strip()


class QueuePanel(QFrame):
    """Lista da fila com editar/cancelar por item e "Limpar fila"."""

    cancelar = pyqtSignal(str)
    editar = pyqtSignal(str)
    limpar = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("queuePanel")
        self._lay = QVBoxLayout(self)
        self._lay.setContentsMargins(8, 7, 8, 8)
        self._lay.setSpacing(5)

        topo = QHBoxLayout()
        topo.setContentsMargins(4, 0, 0, 0)
        self.titulo = QLabel("FILA")
        self.titulo.setObjectName("queueTitle")
        topo.addWidget(self.titulo)
        topo.addStretch(1)
        self.btn_limpar = QToolButton()
        self.btn_limpar.setObjectName("queueClear")
        self.btn_limpar.setText("Limpar fila")
        self.btn_limpar.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_limpar.setToolTip("Cancela todas as mensagens que ainda não foram enviadas")
        self.btn_limpar.clicked.connect(self.limpar.emit)
        topo.addWidget(self.btn_limpar)
        self._lay.addLayout(topo)

        self._itens = []
        self.hide()

    def set_itens(self, itens: list[dict]):
        """`itens`: dicts com `id`, `texto`, `anexos` (rótulos) e `agente`."""
        for widget in self._itens:
            widget.hide()
            widget.deleteLater()
        self._itens = []
        for posicao, item in enumerate(itens, start=1):
            linha = self._linha(posicao, item)
            self._lay.addWidget(linha)
            self._itens.append(linha)
        self.titulo.setText(f"FILA · {len(itens)}")
        self.setVisible(bool(itens))

    def _linha(self, posicao: int, item: dict) -> QFrame:
        linha = QFrame()
        linha.setObjectName("queueItem")
        linha.setProperty("pedido_id", item["id"])
        lay = QHBoxLayout(linha)
        lay.setContentsMargins(7, 5, 5, 5)
        lay.setSpacing(9)

        numero = QLabel(str(posicao))
        numero.setObjectName("queueIndex")
        numero.setAlignment(Qt.AlignmentFlag.AlignCenter)
        numero.setFixedSize(18, 18)
        lay.addWidget(numero)

        texto = QLabel(_resumo(item.get("texto", "")))
        texto.setObjectName("queueText")
        texto.setToolTip(item.get("texto", ""))
        texto.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        lay.addWidget(texto, 1)

        detalhes = []
        anexos = item.get("anexos") or []
        if anexos:
            detalhes.append(f"📎 {len(anexos)} anexo(s)")
        detalhes.append("Agente" if item.get("agente") else "Chat")
        meta = QLabel(" · ".join(detalhes))
        meta.setObjectName("queueMeta")
        if anexos:
            meta.setToolTip("\n".join(anexos))
        lay.addWidget(meta)

        editar = QToolButton()
        editar.setObjectName("queueEdit")
        editar.setText("✎")
        editar.setToolTip("Editar o texto antes de enviar")
        editar.setCursor(Qt.CursorShape.PointingHandCursor)
        editar.clicked.connect(lambda: self.editar.emit(item["id"]))
        lay.addWidget(editar)

        cancelar = QToolButton()
        cancelar.setObjectName("queueCancel")
        cancelar.setText("✕")
        cancelar.setToolTip("Cancelar esta mensagem (não será enviada)")
        cancelar.setCursor(Qt.CursorShape.PointingHandCursor)
        cancelar.clicked.connect(lambda: self.cancelar.emit(item["id"]))
        lay.addWidget(cancelar)
        return linha
