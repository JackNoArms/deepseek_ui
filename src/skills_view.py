"""Aba Habilidades: lista de skills + editor field-based.

Segue o padrão Agent Skills (ADR-017): cada skill é ``skills/<slug>/SKILL.md``
com frontmatter ``name`` + ``description`` e corpo Markdown livre. O estado
(habilitada) mora em ``.deepseek_ui/skills_state.json`` — o editor não toca no
``SKILL.md`` para ligar/desligar.

**Editor field-based.** Nome, Descrição e Conteúdo são campos separados;
YAML do frontmatter e slug (nome da pasta) são gerenciados pelo ``SkillsRepo``.

**Corte de injeção.** Mostra ao usuário qual skill está sendo injetada neste
turno (as ``LIMITE_SKILLS_POR_TURNO`` primeiras habilitadas por slug); as
demais habilitadas aparecem como "fora do limite". O corte real acontece no
``bloco_habilidades`` (``src/prompts.py``).

**Importação rápida.** Botão *Importar* (pasta, ``SKILL.md``/``.md``,
``.zip``/``.skill`` ou texto da área de transferência) e arrastar-e-soltar
na aba. A regra de cópia mora em ``SkillsRepo.importar``.

**Estilo.** Tudo via ``objectName`` no ``theme.py``; nenhum
``setStyleSheet`` inline.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from src.prompts import LIMITE_SKILLS_POR_TURNO
from src.skills import Skill, SkillsRepo


class SkillsView(QWidget):
    """Aba de edição de habilidades no padrão Agent Skills.

    Sinais:
        modificado — emitido depois de qualquer alteração persistida no
            repositório.
    """

    modificado = pyqtSignal()

    def __init__(self, repo: SkillsRepo | None = None, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("skillsPage")
        self.setAcceptDrops(True)
        self.repo = repo
        self._skill_atual: Skill | None = None
        self._populando = False
        self._timer_salvar = QTimer(self)
        self._timer_salvar.setSingleShot(True)
        self._timer_salvar.setInterval(400)
        self._timer_salvar.timeout.connect(self._salvar_atual)
        self._build_ui()
        self._recarregar()

    # ---- construção da UI ------------------------------------------------

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        splitter = QSplitter(Qt.Orientation.Horizontal, self)
        splitter.setChildrenCollapsible(False)
        splitter.addWidget(self._build_list_pane())
        splitter.addWidget(self._build_editor_pane())
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([320, 500])
        root.addWidget(splitter, 1)

    def _build_list_pane(self) -> QWidget:
        pane = QWidget()
        lay = QVBoxLayout(pane)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(6)

        self.lbl_status = QLabel("Abra um projeto para gerenciar habilidades")
        self.lbl_status.setObjectName("skillsStatus")
        self.lbl_status.setWordWrap(True)
        lay.addWidget(self.lbl_status)

        self.edt_busca = QLineEdit()
        self.edt_busca.setPlaceholderText("Buscar habilidade…")
        self.edt_busca.textChanged.connect(self._filtrar)
        lay.addWidget(self.edt_busca)

        self.cmb_filtro = QComboBox()
        self.cmb_filtro.setObjectName("permissionMode")
        self.cmb_filtro.addItem("Todas", "todas")
        self.cmb_filtro.addItem("Habilitadas", "habilitadas")
        self.cmb_filtro.addItem("Desabilitadas", "desabilitadas")
        self.cmb_filtro.currentIndexChanged.connect(self._filtrar)
        lay.addWidget(self.cmb_filtro)

        self.lista = QListWidget()
        self.lista.setObjectName("skillsList")
        self.lista.currentItemChanged.connect(self._on_selecao_mudou)
        lay.addWidget(self.lista, 1)

        botoes = QHBoxLayout()
        botoes.setSpacing(6)
        self.btn_nova = QPushButton("+ Nova")
        self.btn_nova.setToolTip("Cria uma habilidade em branco")
        self.btn_nova.clicked.connect(self._nova)
        botoes.addWidget(self.btn_nova, 1)
        self.btn_importar = QPushButton("⇣ Importar")
        self.btn_importar.setObjectName("skillsImport")
        self.btn_importar.setToolTip(
            "Importa skills no padrão Agent Skills (pasta com SKILL.md, "
            ".md, .zip) — ou arraste para esta aba")
        menu = QMenu(self.btn_importar)
        menu.addAction("Pasta (uma skill ou várias)…", self._importar_pasta)
        menu.addAction("Arquivo SKILL.md, .md ou .zip…", self._importar_arquivo)
        menu.addSeparator()
        menu.addAction("Colar da área de transferência", self._importar_clipboard)
        self.btn_importar.setMenu(menu)
        botoes.addWidget(self.btn_importar, 1)
        lay.addLayout(botoes)

        return pane

    def _build_editor_pane(self) -> QWidget:
        pane = QWidget()
        lay = QVBoxLayout(pane)
        lay.setContentsMargins(12, 8, 12, 12)
        lay.setSpacing(8)

        topo = QHBoxLayout()
        topo.setSpacing(6)
        self.lbl_titulo = QLabel("Selecione uma habilidade")
        self.lbl_titulo.setObjectName("skillsTitle")
        topo.addWidget(self.lbl_titulo, 1)
        self.chk_habilitada = QCheckBox("Habilitada")
        self.chk_habilitada.setToolTip(
            "Habilitada: o conteúdo do SKILL.md vai para o DeepSeek "
            "(até o limite por turno)")
        self.chk_habilitada.toggled.connect(self._alternar_habilitada)
        topo.addWidget(self.chk_habilitada)
        self.btn_duplicar = QPushButton("Duplicar")
        self.btn_duplicar.clicked.connect(self._duplicar)
        topo.addWidget(self.btn_duplicar)
        self.btn_excluir = QPushButton("Excluir")
        self.btn_excluir.setObjectName("danger")
        self.btn_excluir.clicked.connect(self._excluir)
        topo.addWidget(self.btn_excluir)
        lay.addLayout(topo)

        self.lbl_aviso = QLabel("")
        self.lbl_aviso.setObjectName("skillsHint")
        self.lbl_aviso.setWordWrap(True)
        lay.addWidget(self.lbl_aviso)

        # Nome
        lay.addWidget(self._rotulo("Nome"))
        self.edt_nome = QLineEdit()
        self.edt_nome.textChanged.connect(self._agendar_salvar)
        lay.addWidget(self.edt_nome)

        # Descrição
        lay.addWidget(self._rotulo("Descrição"))
        self.edt_descricao = QPlainTextEdit()
        self.edt_descricao.setObjectName("workspaceEditor")
        self.edt_descricao.setFixedHeight(70)
        self.edt_descricao.setPlaceholderText(
            "Usada pelo DeepSeek para decidir se a skill encaixa na tarefa. "
            "Uma ou mais linhas.")
        self.edt_descricao.textChanged.connect(self._agendar_salvar)
        lay.addWidget(self.edt_descricao)

        # Slug readonly
        lay.addWidget(self._rotulo("Slug (identificador)"))
        self.edt_slug = QLineEdit()
        self.edt_slug.setReadOnly(True)
        lay.addWidget(self.edt_slug)

        # Conteúdo
        lay.addWidget(self._rotulo("Conteúdo do SKILL.md (Markdown)"))
        self.edt_conteudo = QPlainTextEdit()
        self.edt_conteudo.setObjectName("workspaceEditor")
        self.edt_conteudo.textChanged.connect(self._agendar_salvar)
        lay.addWidget(self.edt_conteudo, 1)

        self.lbl_salvo = QLabel("")
        self.lbl_salvo.setObjectName("skillsSaved")
        lay.addWidget(self.lbl_salvo)

        return pane

    def _rotulo(self, texto: str) -> QLabel:
        lbl = QLabel(texto.upper())
        lbl.setObjectName("fieldLabel")
        return lbl

    # ---- API pública -----------------------------------------------------

    def set_repo(self, repo: SkillsRepo | None):
        self.repo = repo
        self._skill_atual = None
        self._recarregar()

    # ---- carregamento ---------------------------------------------------

    def _recarregar(self):
        self._populando = True
        self.lista.clear()
        try:
            if self.repo is None:
                self.lbl_status.setText(
                    "Abra um projeto para gerenciar habilidades.")
                self._limpar_editor()
                self._habilitar_editor(False)
                return
            skills = self.repo.all()
            self._popular(skills)
            self._atualizar_status(skills)
        finally:
            self._populando = False
        self._atualizar_selecao_inicial()

    def _popular(self, skills: list[Skill]):
        for s in skills:
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, s.slug)
            widget = self._build_item_widget(s)
            item.setSizeHint(widget.sizeHint())
            self.lista.addItem(item)
            self.lista.setItemWidget(item, widget)

    def _build_item_widget(self, skill: Skill) -> QWidget:
        from PyQt6.QtWidgets import QFrame
        w = QFrame()
        w.setObjectName("skillsItem")
        w.setProperty("habilitada", "true" if skill.habilitada else "false")
        w.setProperty("selecionado", "false")
        w.setCursor(Qt.CursorShape.PointingHandCursor)
        lay = QHBoxLayout(w)
        lay.setContentsMargins(8, 6, 8, 6)
        lay.setSpacing(10)

        badge = QLabel(self._iniciais(skill.name))
        badge.setObjectName("skillsIcon")
        badge.setFixedSize(32, 32)
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(badge)

        col = QVBoxLayout()
        col.setSpacing(1)
        nome = QLabel(skill.name)
        nome.setObjectName("skillsItemName")
        nome.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        col.addWidget(nome)
        desc = QLabel(self._truncar(skill.description, 70))
        desc.setObjectName("skillsItemDesc")
        desc.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        col.addWidget(desc)
        lay.addLayout(col, 1)

        return w

    def _atualizar_status(self, skills: list[Skill]):
        total = len(skills)
        if total == 0:
            self.lbl_status.setText(
                "Nenhuma habilidade cadastrada. Clique em + Nova, Importar "
                "ou arraste uma pasta com SKILL.md para cá.")
            return
        habilitadas = sorted(
            (s for s in skills if s.habilitada), key=lambda s: s.slug)
        n_hab = len(habilitadas)
        n_inj = min(n_hab, LIMITE_SKILLS_POR_TURNO)
        excedente = n_hab - n_inj
        txt = f"{n_hab} de {total} habilitadas · {n_inj} injetada"
        txt += "s" if n_inj != 1 else ""
        txt += " neste turno"
        if excedente > 0:
            txt += f" · {excedente} além do limite"
        self.lbl_status.setText(txt)

    def _atualizar_selecao_inicial(self):
        if self.lista.count() == 0:
            self._skill_atual = None
            self._limpar_editor()
            self._habilitar_editor(False)
            return
        if self.lista.currentRow() < 0:
            self.lista.setCurrentRow(0)

    def _filtrar(self):
        termo = self.edt_busca.text().strip().lower()
        filtro = self.cmb_filtro.currentData() or "todas"
        for i in range(self.lista.count()):
            item = self.lista.item(i)
            slug = item.data(Qt.ItemDataRole.UserRole)
            skill = self.repo.by_slug(slug) if self.repo else None
            if skill is None:
                item.setHidden(True)
                continue
            if filtro == "habilitadas" and not skill.habilitada:
                item.setHidden(True)
                continue
            if filtro == "desabilitadas" and skill.habilitada:
                item.setHidden(True)
                continue
            if termo:
                alvo = f"{skill.name} {skill.description} {skill.slug}".lower()
                item.setHidden(termo not in alvo)
                continue
            item.setHidden(False)

    # ---- eventos da lista -----------------------------------------------

    def _on_selecao_mudou(self, atual, _anterior):
        # Marca o widget selecionado e desmarca os demais
        for i in range(self.lista.count()):
            it = self.lista.item(i)
            w = self.lista.itemWidget(it)
            if w is not None and w.objectName() == "skillsItem":
                w.setProperty("selecionado",
                              "true" if it is atual else "false")
                w.style().unpolish(w)
                w.style().polish(w)
        if self._populando or atual is None:
            return
        slug = atual.data(Qt.ItemDataRole.UserRole)
        if not slug or self.repo is None:
            return
        skill = self.repo.by_slug(slug)
        if skill is None:
            return
        self._skill_atual = skill
        self._carregar_no_editor(skill)

    # ---- editor ---------------------------------------------------------

    def _carregar_no_editor(self, skill: Skill):
        self._populando = True
        try:
            self.edt_nome.setText(skill.name)
            self.edt_descricao.setPlainText(skill.description)
            self.edt_slug.setText(f"skills/{skill.slug}/SKILL.md")
            self.chk_habilitada.setChecked(skill.habilitada)
            self.edt_conteudo.setPlainText(skill.conteudo)
            self.lbl_titulo.setText(skill.name or "(sem nome)")
            self._atualizar_aviso(skill)
            self.lbl_salvo.setText("")
        finally:
            self._populando = False
        self._habilitar_editor(True)

    def _atualizar_aviso(self, skill: Skill):
        todas = self.repo.all() if self.repo else []
        habilitadas = sorted(
            (s for s in todas if s.habilitada), key=lambda s: s.slug)
        slugs_injetadas = {s.slug for s in habilitadas[:LIMITE_SKILLS_POR_TURNO]}
        if skill.habilitada and skill.slug in slugs_injetadas:
            self.lbl_aviso.setObjectName("skillsHintOn")
            self.lbl_aviso.setText(
                "Habilitada e injetada — o conteúdo deste SKILL.md vai para o "
                "DeepSeek no próximo envio.")
        elif skill.habilitada:
            self.lbl_aviso.setObjectName("skillsHint")
            self.lbl_aviso.setText(
                f"Habilitada, mas fora do limite de "
                f"{LIMITE_SKILLS_POR_TURNO} skills por turno. Desabilite outra "
                "ou reordene (o corte é alfabético por slug).")
        else:
            self.lbl_aviso.setObjectName("skillsHintOff")
            self.lbl_aviso.setText(
                "Desabilitada — o DeepSeek vê só nome e descrição no índice; "
                "o conteúdo do SKILL.md não é enviado.")
        self.lbl_aviso.style().unpolish(self.lbl_aviso)
        self.lbl_aviso.style().polish(self.lbl_aviso)

    def _limpar_editor(self):
        self._populando = True
        try:
            self.edt_nome.clear()
            self.edt_descricao.clear()
            self.edt_slug.clear()
            self.edt_conteudo.clear()
            self.chk_habilitada.setChecked(False)
            self.lbl_titulo.setText("Selecione uma habilidade")
            self.lbl_aviso.clear()
            self.lbl_aviso.setObjectName("skillsHint")
            self.lbl_aviso.style().unpolish(self.lbl_aviso)
            self.lbl_aviso.style().polish(self.lbl_aviso)
            self.lbl_salvo.clear()
            self.lbl_salvo.setObjectName("skillsSaved")
            self.lbl_salvo.style().unpolish(self.lbl_salvo)
            self.lbl_salvo.style().polish(self.lbl_salvo)
        finally:
            self._populando = False

    def _habilitar_editor(self, on: bool):
        for w in (self.edt_nome, self.edt_descricao, self.edt_conteudo,
                  self.btn_duplicar, self.btn_excluir, self.chk_habilitada):
            w.setEnabled(on)

    def _agendar_salvar(self):
        if self._populando or self._skill_atual is None:
            return
        self._timer_salvar.start()

    def _salvar_atual(self):
        if self._skill_atual is None or self.repo is None:
            return
        s = self._skill_atual
        s.name = self.edt_nome.text().strip() or s.slug
        s.description = self.edt_descricao.toPlainText().strip()
        s.conteudo = self.edt_conteudo.toPlainText()
        try:
            self.repo.save(s)
        except OSError as e:
            self.lbl_salvo.setObjectName("skillsSavedError")
            self.lbl_salvo.setText(f"Falha ao salvar: {e}")
            self.lbl_salvo.style().unpolish(self.lbl_salvo)
            self.lbl_salvo.style().polish(self.lbl_salvo)
            return
        self.lbl_salvo.setObjectName("skillsSaved")
        self.lbl_salvo.setText("salvo ✓")
        self.lbl_salvo.style().unpolish(self.lbl_salvo)
        self.lbl_salvo.style().polish(self.lbl_salvo)
        self.lbl_titulo.setText(s.name)
        self._atualizar_item_na_lista(s)
        self._atualizar_status(self.repo.all())
        self.modificado.emit()

    def _atualizar_item_na_lista(self, skill: Skill):
        self._populando = True
        try:
            for i in range(self.lista.count()):
                item = self.lista.item(i)
                if item.data(Qt.ItemDataRole.UserRole) == skill.slug:
                    w = self._build_item_widget(skill)
                    item.setSizeHint(w.sizeHint())
                    self.lista.setItemWidget(item, w)
                    break
        finally:
            self._populando = False

    # ---- ações ----------------------------------------------------------

    def _alternar_habilitada(self, ligada: bool):
        if self._populando or self.repo is None or self._skill_atual is None:
            return
        skill = self.repo.set_habilitada(self._skill_atual.slug, ligada)
        if skill is None:
            return
        self._skill_atual = skill
        self._atualizar_aviso(skill)
        self._atualizar_item_na_lista(skill)
        self._atualizar_status(self.repo.all())
        self.modificado.emit()

    # ---- importação -----------------------------------------------------

    def _importar_pasta(self):
        if self.repo is None:
            return
        pasta = QFileDialog.getExistingDirectory(
            self, "Importar habilidades — escolha a pasta da skill ou a que "
            "contém várias")
        if pasta:
            self.importar_caminhos([pasta])

    def _importar_arquivo(self):
        if self.repo is None:
            return
        caminhos, _ = QFileDialog.getOpenFileNames(
            self, "Importar habilidades", "",
            "Skills (SKILL.md *.md *.markdown *.zip *.skill);;Todos (*)")
        if caminhos:
            self.importar_caminhos(caminhos)

    def _importar_clipboard(self):
        if self.repo is None:
            return
        dados = QGuiApplication.clipboard().mimeData()
        if dados is not None and dados.hasUrls():
            caminhos = [u.toLocalFile() for u in dados.urls() if u.isLocalFile()]
            if caminhos:
                self.importar_caminhos(caminhos)
                return
        texto = QGuiApplication.clipboard().text()
        self.importar_texto(texto)

    def importar_texto(self, texto: str):
        """Cria uma skill com o Markdown colado/solto na aba."""
        if self.repo is None:
            return
        if not (texto or "").strip():
            self.lbl_status.setText(
                "Área de transferência vazia — copie o conteúdo de um SKILL.md.")
            return
        skill = self.repo.importar_texto(texto)
        self._concluir_importacao([skill] if skill else [], [])

    def importar_caminhos(self, caminhos):
        """Importa pastas/arquivos e seleciona a primeira skill nova."""
        if self.repo is None:
            return
        importadas, ignorados = [], []
        for caminho in caminhos:
            resultado = self.repo.importar(caminho)
            importadas += resultado.importadas
            ignorados += resultado.ignorados
        self._concluir_importacao(importadas, ignorados)

    def _concluir_importacao(self, importadas, ignorados):
        self._recarregar()
        if importadas:
            primeira = importadas[0].slug
            for i in range(self.lista.count()):
                if self.lista.item(i).data(Qt.ItemDataRole.UserRole) == primeira:
                    self.lista.setCurrentRow(i)
                    break
            self.modificado.emit()
        partes = []
        if importadas:
            nomes = ", ".join(s.name for s in importadas[:4])
            if len(importadas) > 4:
                nomes += f" e mais {len(importadas) - 4}"
            partes.append(f"✓ {len(importadas)} importada(s): {nomes}. "
                          "Marque Habilitada para usar.")
        if ignorados:
            partes.append("Ignorado: " + "; ".join(ignorados[:3]))
        if not partes:
            partes.append("Nada para importar.")
        self.lbl_status.setText(" ".join(partes))

    def dragEnterEvent(self, event):
        dados = event.mimeData()
        if self.repo is not None and (dados.hasUrls() or dados.hasText()):
            self.setProperty("arrastando", True)
            self.style().unpolish(self)
            self.style().polish(self)
            event.acceptProposedAction()
            return
        event.ignore()

    def dragLeaveEvent(self, event):
        self._fim_arraste()
        super().dragLeaveEvent(event)

    def dropEvent(self, event):
        self._fim_arraste()
        dados = event.mimeData()
        if dados.hasUrls():
            caminhos = [u.toLocalFile() for u in dados.urls() if u.isLocalFile()]
            if caminhos:
                self.importar_caminhos(caminhos)
                event.acceptProposedAction()
                return
        if dados.hasText():
            self.importar_texto(dados.text())
            event.acceptProposedAction()

    def _fim_arraste(self):
        self.setProperty("arrastando", False)
        self.style().unpolish(self)
        self.style().polish(self)

    def _nova(self):
        if self.repo is None:
            return
        slug = self.repo.novo_slug("Nova habilidade")
        s = Skill(
            slug=slug,
            name="Nova habilidade",
            description="",
            conteudo="# Nova habilidade\n\n## 0. Regras de ouro\n\n"
                     "## Mapa do fluxo\n\n## Antipadrões\n",
        )
        self.repo.save(s)
        self._recarregar()
        for i in range(self.lista.count()):
            if self.lista.item(i).data(Qt.ItemDataRole.UserRole) == slug:
                self.lista.setCurrentRow(i)
                break
        self.edt_nome.setFocus()
        self.edt_nome.selectAll()
        self.modificado.emit()

    def _duplicar(self):
        if self.repo is None or self._skill_atual is None:
            return
        s = self._skill_atual
        slug = self.repo.novo_slug(s.name + " copia")
        copia = Skill(
            slug=slug,
            name=s.name + " (cópia)",
            description=s.description,
            conteudo=s.conteudo,
            habilitada=False,
        )
        self.repo.save(copia)
        self._recarregar()
        for i in range(self.lista.count()):
            if self.lista.item(i).data(Qt.ItemDataRole.UserRole) == slug:
                self.lista.setCurrentRow(i)
                break
        self.modificado.emit()

    def _excluir(self):
        if self.repo is None or self._skill_atual is None:
            return
        s = self._skill_atual
        r = QMessageBox.question(
            self, "Excluir habilidade",
            f"Excluir \"{s.name}\"?\n\nA pasta skills/{s.slug}/ será apagada.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if r != QMessageBox.StandardButton.Yes:
            return
        self.repo.delete(s.slug)
        self._skill_atual = None
        self._recarregar()
        self.modificado.emit()

    # ---- helpers --------------------------------------------------------

    @staticmethod
    def _iniciais(name: str) -> str:
        limpo = (name or "").strip()
        if not limpo:
            return "??"
        partes = [p for p in limpo.replace("_", "-").split("-") if p]
        if len(partes) >= 2:
            return (partes[0][0] + partes[1][0]).upper()
        return limpo[:2].upper()

    @staticmethod
    def _truncar(texto: str, max_chars: int) -> str:
        if not texto:
            return ""
        t = " ".join(str(texto).split())
        if len(t) <= max_chars:
            return t
        return t[: max_chars - 1].rstrip() + "…"
