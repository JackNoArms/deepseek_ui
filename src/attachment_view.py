"""Preview a pending attachment before it is sent to DeepSeek."""

from pathlib import Path

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QImageReader, QPixmap
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QPlainTextEdit,
    QVBoxLayout,
)

from src.anexos import EXT_TEXTO

MAX_PREVIEW_BYTES = 512_000


class AttachmentPreviewDialog(QDialog):
    def __init__(self, attachment, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Prévia do anexo — {attachment.rotulo}")
        self.resize(900, 720)
        layout = QVBoxLayout(self)

        if attachment.modo == "inline":
            content = QPlainTextEdit()
            content.setReadOnly(True)
            content.setPlainText(attachment.conteudo or "")
            layout.addWidget(content, 1)
        elif attachment.caminho:
            path = Path(attachment.caminho)
            texto_mostrado = False
            if path.suffix.lower() in EXT_TEXTO or not path.suffix:
                try:
                    with path.open("rb") as arquivo:
                        data = arquivo.read(MAX_PREVIEW_BYTES + 1)
                except OSError as error:
                    layout.addWidget(QLabel(
                        f"Não foi possível ler uma prévia de {attachment.rotulo}: "
                        f"{error}"))
                    texto_mostrado = True
                else:
                    if b"\x00" not in data:
                        texto = data[:MAX_PREVIEW_BYTES].decode(
                            "utf-8", errors="replace")
                        content = QPlainTextEdit()
                        content.setReadOnly(True)
                        content.setPlainText(texto)
                        layout.addWidget(content, 1)
                        texto_mostrado = True
                        if len(data) > MAX_PREVIEW_BYTES:
                            layout.addWidget(QLabel(
                                f"Prévia limitada aos primeiros "
                                f"{MAX_PREVIEW_BYTES:,} bytes."))

            if not texto_mostrado:
                reader = QImageReader(str(path))
                dimensoes = reader.size()
                if dimensoes.isValid():
                    reader.setScaledSize(dimensoes.scaled(
                        QSize(860, 620), Qt.AspectRatioMode.KeepAspectRatio))
                image = reader.read()
                if image.isNull():
                    preview = QLabel(
                        "Não foi possível exibir uma prévia deste arquivo.\n"
                        f"{reader.errorString()}")
                else:
                    preview = QLabel()
                    preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
                    preview.setPixmap(QPixmap.fromImage(image))
                layout.addWidget(preview, 1)
                try:
                    tamanho = path.stat().st_size
                    layout.addWidget(QLabel(
                        f"{attachment.rotulo} · {dimensoes.width()}×"
                        f"{dimensoes.height()} · {tamanho:,} bytes"))
                except OSError as error:
                    layout.addWidget(QLabel(
                        f"{attachment.rotulo} · não consegui ler os detalhes: {error}"))
        else:
            layout.addWidget(QLabel("Este anexo não tem conteúdo para visualizar."))

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)
