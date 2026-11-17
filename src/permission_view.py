"""Diálogo para configurar o escopo e as operações autorizadas."""

import os

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QComboBox,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QWidget,
    QVBoxLayout,
)

from src.permissions import FolderGrant, PermissionPolicy
from src.sandbox import SandboxError

MODOS_UI = [
    ("Projeto aberto (revisar cada ação)", "project_confirm"),
    ("Projeto + vault vinculado (automático)", "project_auto"),
    ("Pastas escolhidas (permissões por operação)", "folders"),
    ("Computador todo (confirmar cada ação)", "computer_confirm"),
    ("Computador todo (automático)", "computer_auto"),
]
OPERACOES = (("Ler", "read"), ("Criar", "create"),
             ("Editar", "edit"), ("Apagar", "delete"))


class PermissionDialog(QDialog):
    """Edita permissões CRUD/leitura e o perfil ativo do projeto."""

    def __init__(self, project, parent=None):
        super().__init__(parent)
        self.project = project
        self.setWindowTitle("Permissões do agente")
        self.resize(900, 620)
        self.setMinimumSize(760, 520)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        self.lbl_scope = QLabel("1. Escopo de acesso")
        self.lbl_scope.setObjectName("permissionSection")
        layout.addWidget(self.lbl_scope)
        self.mode = QComboBox()
        self.mode.setObjectName("permissionMode")
        for label, value in MODOS_UI:
            self.mode.addItem(label, value)
        index = self.mode.findData(project.permissions.mode)
        self.mode.setCurrentIndex(max(index, 0))
        self.mode.currentIndexChanged.connect(self._atualizar_aviso)
        layout.addWidget(self.mode)

        self.aviso = QLabel()
        self.aviso.setObjectName("permissionNotice")
        self.aviso.setWordWrap(True)
        layout.addWidget(self.aviso)
        self.confirm_reads = QCheckBox(
            "Pedir confirmação antes de compartilhar leituras/estrutura com o DeepSeek")
        self._label_confirm_reads = self.confirm_reads.text()
        self._confirm_reads_preference = project.permissions.confirm_reads
        self.confirm_reads.setChecked(self._confirm_reads_preference)
        self.confirm_reads.toggled.connect(self._guardar_preferencia_leitura)
        self.confirm_reads.setToolTip(
            "Confirma o mapa de arquivos enviado junto ao pedido e, no modo "
            "Agente, cada leitura, listagem ou busca antes de compartilhar o "
            "resultado com o DeepSeek.")
        layout.addWidget(self.confirm_reads)
        self.grants_info = QLabel()
        self.grants_info.setObjectName("permissionHint")
        self.grants_info.setWordWrap(True)
        layout.addWidget(self.grants_info)
        explicacao = QLabel(
            "Projeto + vault automático dispensa confirmação para leitura e CRUD "
            "somente no projeto e no vault vinculado; comandos ainda pedem "
            "confirmação. Pastas escolhidas e Computador automático executam "
            "qualquer comando sem confirmação, no shell, a partir da raiz do "
            "projeto. "
            "Os grants controlam operações de arquivo do app, mas não confinam "
            "os efeitos dos processos. Arquivos alterados pelo app mantêm backup; "
            "nenhum perfil automático é um sandbox do Windows.")
        explicacao.setWordWrap(True)
        layout.addWidget(explicacao)

        self.tabela = QTableWidget(0, 1 + len(OPERACOES))
        self.tabela.setObjectName("permissionGrants")
        self.tabela.setAlternatingRowColors(True)
        self.tabela.setMinimumHeight(190)
        self.tabela.setShowGrid(False)
        self.tabela.setWordWrap(False)
        self.tabela.setToolTip(
            "Marque as operações permitidas em cada pasta. "
            "Essas regras só ficam ativas no perfil Pastas escolhidas.")
        self.tabela.setHorizontalHeaderLabels(
            ["Pasta autorizada"] + [nome for nome, _ in OPERACOES])
        header = self.tabela.horizontalHeader()
        if header is not None:
            header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
            for coluna in range(1, self.tabela.columnCount()):
                header.setSectionResizeMode(
                    coluna, QHeaderView.ResizeMode.ResizeToContents)
        self.tabela.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows)
        self.tabela.setSelectionMode(
            QTableWidget.SelectionMode.SingleSelection)
        layout.addWidget(self.tabela, 1)

        controles = QHBoxLayout()
        btn_add = QPushButton("Adicionar pasta")
        btn_add.clicked.connect(self._adicionar_pasta)
        controles.addWidget(btn_add)
        btn_remove = QPushButton("Remover pasta")
        btn_remove.clicked.connect(self._remover_pasta)
        controles.addWidget(btn_remove)
        controles.addStretch(1)
        layout.addLayout(controles)

        for regra in project.permissions.grants:
            self._adicionar_regra(regra)
        if not any(
                os_path_equal(self._caminho_linha(linha), str(project.root))
                for linha in range(self.tabela.rowCount())):
            self._adicionar_regra({
                "path": str(project.root), "read": True,
                "create": False, "edit": False, "delete": False,
            })

        botoes = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        botoes.accepted.connect(self.accept)
        botoes.rejected.connect(self.reject)
        layout.addWidget(botoes)
        self._atualizar_aviso()

    def _caminho_linha(self, linha):
        item = self.tabela.item(linha, 0)
        return item.text() if item else ""

    def _adicionar_regra(self, regra: FolderGrant):
        linha = self.tabela.rowCount()
        self.tabela.insertRow(linha)
        caminho = str(regra["path"])
        item = QTableWidgetItem(caminho)
        item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
        self.tabela.setItem(linha, 0, item)
        for coluna, (_, chave) in enumerate(OPERACOES, 1):
            celula = QWidget()
            celula_lay = QHBoxLayout(celula)
            celula_lay.setContentsMargins(0, 0, 0, 0)
            celula_lay.addStretch(1)
            caixa = QCheckBox()
            caixa.setObjectName("folderPermission")
            caixa.setAccessibleName(f"{OPERACOES[coluna - 1][0]}: {caminho}")
            caixa.setToolTip(f"{OPERACOES[coluna - 1][0]} em {caminho}")
            caixa.setChecked(regra.get(chave, False))
            caixa.setMinimumSize(32, 32)
            celula_lay.addWidget(caixa)
            celula_lay.addStretch(1)
            self.tabela.setCellWidget(linha, coluna, celula)

    def _adicionar_pasta(self):
        pasta = QFileDialog.getExistingDirectory(
            self, "Escolher pasta autorizada", str(self.project.root))
        if not pasta:
            return
        try:
            regra: FolderGrant = {
                "path": pasta, "read": True, "create": False,
                "edit": False, "delete": False,
            }
            PermissionPolicy(self.project.root, "folders", [regra])
        except (ValueError, SandboxError) as e:
            QMessageBox.warning(self, "Pasta não autorizada", str(e))
            return
        if any(os_path_equal(self._caminho_linha(i), pasta)
               for i in range(self.tabela.rowCount())):
            return
        self._adicionar_regra(regra)

    def _remover_pasta(self):
        linha = self.tabela.currentRow()
        if linha < 0:
            return
        if os_path_equal(self._caminho_linha(linha), str(self.project.root)):
            QMessageBox.information(
                self, "Pasta do projeto", "A raiz do projeto não pode ser removida.")
            return
        self.tabela.removeRow(linha)

    def _atualizar_aviso(self, *_):
        modo = self.mode.currentData()
        avisos = {
            "project_confirm": (
                "Somente a raiz do projeto. Criar, editar, apagar e executar "
                "comandos exigem confirmação."),
            "project_auto": (
                "Leitura e CRUD automáticos somente no projeto e no vault "
                "vinculado. Backups continuam ativos; comandos ainda exigem "
                "confirmação."),
            "folders": (
                "Marque Ler/Criar/Editar/Apagar por pasta para autorizar o escopo. "
                "As operações marcadas são aplicadas sem confirmação adicional; "
                "as não marcadas continuam bloqueadas. Qualquer comando roda sem "
                "confirmação, no shell, a partir da raiz do projeto — e não fica "
                "confinado às pastas marcadas."),
            "computer_confirm": (
                "Acesso amplo, exceto caminhos críticos do Windows. Escritas e "
                "comandos ainda exigem confirmação."),
            "computer_auto": (
                "Sem confirmação por ação. Qualquer comando roda direto no shell, "
                "sem lista de permitidos — comando não tem backup nem desfazer. "
                "O bloqueio de pastas críticas vale para as ações de arquivo do "
                "app, não para o que um comando faz."),
        }
        self.aviso.setText(avisos[modo])
        self.grants_info.setText(
            "As caixas podem ser configuradas agora. Elas só autorizam operações "
            "quando o escopo “Pastas escolhidas” estiver selecionado."
            if modo != "folders" else
            "Marque as operações por pasta. Operações permitidas são aplicadas "
            "sem confirmação adicional; as não marcadas continuam bloqueadas. "
            "Para notas novas, marque Criar; Editar vale para arquivos existentes.")
        self.confirm_reads.setEnabled(modo != "project_auto")
        self.confirm_reads.blockSignals(True)
        self.confirm_reads.setChecked(
            False if modo == "project_auto" else self._confirm_reads_preference)
        self.confirm_reads.blockSignals(False)
        self.confirm_reads.setText(
            "Leituras automáticas neste perfil"
            if modo == "project_auto" else self._label_confirm_reads)

    def _guardar_preferencia_leitura(self, marcado: bool):
        if self.mode.currentData() != "project_auto":
            self._confirm_reads_preference = marcado

    def settings(self) -> dict:
        grants = []
        for linha in range(self.tabela.rowCount()):
            regra: FolderGrant = {
                "path": self._caminho_linha(linha), "read": False,
                "create": False, "edit": False, "delete": False,
            }
            for coluna, (_, chave) in enumerate(OPERACOES, 1):
                celula = self.tabela.cellWidget(linha, coluna)
                caixa = celula.findChild(QCheckBox) if celula else None
                if caixa is None:
                    raise RuntimeError("Célula de permissão ausente na tabela.")
                regra[chave] = caixa.isChecked()
            grants.append(regra)
        return {
            "mode": self.mode.currentData(),
            "grants": grants,
            "confirm_reads": (
                self._confirm_reads_preference
                if self.mode.currentData() == "project_auto"
                else self.confirm_reads.isChecked()),
        }


def os_path_equal(a: str, b: str) -> bool:
    return os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))
