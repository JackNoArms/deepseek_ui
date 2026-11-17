"""Small forms for creating notes and editing workspace text files."""

from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QVBoxLayout,
)


class TextFileDialog(QDialog):
    def __init__(self, title: str, path: str, text: str, parent=None):
        super().__init__(parent)
        self.setObjectName("textFileDialog")
        self.setWindowTitle(title)
        self.resize(900, 640)
        layout = QVBoxLayout(self)
        cabecalho = QVBoxLayout()
        cabecalho.setSpacing(3)
        nome = QLabel(path.replace("\\", "/").rsplit("/", 1)[-1])
        nome.setObjectName("fileDialogTitle")
        cabecalho.addWidget(nome)
        local = QLabel(path)
        local.setObjectName("fileDialogPath")
        local.setWordWrap(True)
        cabecalho.addWidget(local)
        layout.addLayout(cabecalho)
        self.editor = QPlainTextEdit()
        self.editor.setObjectName("workspaceEditor")
        self.editor.setPlainText(text)
        self.editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        layout.addWidget(self.editor, 1)
        tipo = path.rsplit(".", 1)[-1].upper() if "." in path else "TEXTO"
        formato = QLabel(f"{tipo} · UTF-8 · texto plano")
        formato.setObjectName("fileDialogFormat")
        layout.addWidget(formato)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def text(self) -> str:
        return self.editor.toPlainText()


class NewNoteDialog(QDialog):
    TIPOS = (
        ("Nota", "nota", "Notas"),
        ("Decisão", "decisao", "Decisões"),
        ("Plano", "plano", "Planos"),
        ("Referência", "referencia", "Referência"),
        ("Registro", "registro", "Diário"),
    )

    def __init__(self, pasta_inicial: str = "", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Criar nota do vault")
        self.resize(620, 620)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        layout.addLayout(form)

        self.title_input = QLineEdit()
        self.title_input.setPlaceholderText("Ex.: Decisão sobre o armazenamento")
        form.addRow("Título", self.title_input)

        self.type_input = QComboBox()
        for label, tipo, pasta in self.TIPOS:
            self.type_input.addItem(label, (tipo, pasta))
        self.type_input.currentIndexChanged.connect(self._atualizar_pasta)
        form.addRow("Tipo", self.type_input)

        self.folder_input = QLineEdit(pasta_inicial)
        form.addRow("Pasta", self.folder_input)

        self.tags_input = QLineEdit()
        self.tags_input.setPlaceholderText("projeto, arquitetura (separadas por vírgula)")
        form.addRow("Tags", self.tags_input)

        self.context_input = QPlainTextEdit()
        self.context_input.setPlaceholderText(
            "Por que esta nota existe? Qual é o contexto e a origem?")
        self.context_input.setMaximumHeight(110)
        form.addRow("Contexto", self.context_input)

        self.content_input = QPlainTextEdit()
        self.content_input.setPlaceholderText(
            "Conteúdo, decisão, procedimento ou fatos verificados…")
        form.addRow("Conteúdo", self.content_input)

        layout.addWidget(QLabel(
            "A nota será criada com frontmatter YAML e datas ISO; a gravação "
            "fica em backup antes de qualquer edição ou exclusão."))
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _atualizar_pasta(self, indice: int):
        _tipo, pasta = self.type_input.itemData(indice)
        if not self.folder_input.text().strip():
            self.folder_input.setText(pasta)

    def details(self) -> dict[str, str]:
        tipo, _pasta = self.type_input.currentData()
        return {
            "title": self.title_input.text().strip(),
            "type": tipo,
            "folder": self.folder_input.text().strip(),
            "tags": self.tags_input.text(),
            "context": self.context_input.toPlainText(),
            "content": self.content_input.toPlainText(),
        }
