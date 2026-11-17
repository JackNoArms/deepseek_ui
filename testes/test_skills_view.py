"""Smoke tests da aba Habilidades (``src/skills_view.py``) no padrão Agent Skills.

Sem servidor nem projeto real: cria um ``SkillsRepo`` num diretório
temporário e monta a view com ``QT_QPA_PLATFORM=offscreen``. Cobrem:
view vazia, popular, selecionar, editar (nome/descrição/conteúdo), nova,
duplicar, excluir, banner do limite, iniciais do badge.

A ``QApplication`` vem de ``pytest_sessionstart`` no ``conftest.py``.
"""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QLabel

from src.skills import Skill, SkillsRepo
from src.skills_view import SkillsView


def _repo(tmp_path, *specs):
    repo = SkillsRepo(tmp_path, bootstrap=False)
    for spec in specs:
        repo.save(Skill(**spec))
    return repo


def _find_item(v, slug):
    for i in range(v.lista.count()):
        item = v.lista.item(i)
        if item.data(Qt.ItemDataRole.UserRole) == slug:
            return item
    return None


def _achar_badge(w):
    for lbl in w.findChildren(QLabel):
        if lbl.objectName() == "skillsIcon":
            return lbl.text()
    return None


# ---- vazia ---------------------------------------------------------

def test_view_sem_repo_nao_explode(qt_app):
    v = SkillsView(None)
    assert v.lista.count() == 0
    assert "abra um projeto" in v.lbl_status.text().lower()


def test_view_com_repo_popula(qt_app, tmp_path):
    repo = _repo(tmp_path, dict(slug="alpha", name="Alpha", description="desc"))
    v = SkillsView(repo)
    assert v.lista.count() == 1
    item = v.lista.item(0)
    assert item.data(Qt.ItemDataRole.UserRole) == "alpha"


def test_view_mostra_iniciais_do_nome(qt_app, tmp_path):
    repo = _repo(
        tmp_path,
        dict(slug="backend-dev", name="backend-dev", description="x"),
        dict(slug="alfabeto", name="Alfabeto", description="y"),
    )
    v = SkillsView(repo)
    # Busca por slug (all() ordena alfabeticamente, não por inserção)
    item_bd = _find_item(v, "backend-dev")
    item_al = _find_item(v, "alfabeto")
    assert item_bd is not None and item_al is not None
    assert _achar_badge(v.lista.itemWidget(item_bd)) == "BD"
    assert _achar_badge(v.lista.itemWidget(item_al)) == "AL"


# ---- seleção / editor ------------------------------------------------

def test_selecionar_carrega_editor(qt_app, tmp_path):
    repo = _repo(tmp_path, dict(
        slug="alvo", name="Alvo", description="desc alvo",
        conteudo="# corpo alvo\n",
    ))
    v = SkillsView(repo)
    v.lista.setCurrentRow(0)
    assert v._skill_atual is not None
    assert v._skill_atual.slug == "alvo"
    assert v.edt_nome.text() == "Alvo"
    assert v.edt_descricao.toPlainText() == "desc alvo"
    assert "# corpo alvo" in v.edt_conteudo.toPlainText()
    assert v.edt_slug.text() == "skills/alvo/SKILL.md"


def test_salvar_edicao_persiste(qt_app, tmp_path):
    repo = _repo(tmp_path, dict(
        slug="alvo", name="Alvo", description="antiga",
        conteudo="corpo velho\n",
    ))
    v = SkillsView(repo)
    v.lista.setCurrentRow(0)
    v.edt_nome.setText("Alvo Renomeado")
    v.edt_descricao.setPlainText("nova desc")
    v.edt_conteudo.setPlainText("corpo novo\n")
    v._salvar_atual()
    relido = SkillsRepo(tmp_path, bootstrap=False).load()[0]
    assert relido.name == "Alvo Renomeado"
    assert relido.description == "nova desc"
    assert "corpo novo" in relido.conteudo


# ---- toggle via state (integração) -----------------------------------

def test_habilitar_via_repo_reflete_no_status(qt_app, tmp_path):
    repo = _repo(tmp_path, dict(slug="a", name="A", habilitada=False))
    v = SkillsView(repo)
    assert "0 de 1" in v.lbl_status.text()
    repo.set_habilitada("a", True)
    v._recarregar()
    assert "1 de 1" in v.lbl_status.text()


# ---- banner do limite ------------------------------------------------

def test_banner_fora_do_limite(qt_app, tmp_path):
    repo = _repo(
        tmp_path,
        dict(slug="a", name="A", habilitada=True, conteudo="a\n"),
        dict(slug="b", name="B", habilitada=True, conteudo="b\n"),
        dict(slug="c", name="C", habilitada=True, conteudo="c\n"),
    )
    v = SkillsView(repo)
    item_c = _find_item(v, "c")
    assert item_c is not None
    v.lista.setCurrentItem(item_c)
    assert "fora do limite" in v.lbl_aviso.text().lower()


def test_banner_injetada(qt_app, tmp_path):
    repo = _repo(tmp_path, dict(
        slug="a", name="A", habilitada=True, conteudo="a\n"))
    v = SkillsView(repo)
    v.lista.setCurrentRow(0)
    assert "injetada" in v.lbl_aviso.text().lower()


def test_banner_desabilitada(qt_app, tmp_path):
    repo = _repo(tmp_path, dict(slug="a", name="A", habilitada=False))
    v = SkillsView(repo)
    v.lista.setCurrentRow(0)
    assert "desabilitada" in v.lbl_aviso.text().lower()


# ---- ações -------------------------------------------------------------

def test_set_repo_none_limpa(qt_app, tmp_path):
    repo = _repo(tmp_path, dict(slug="a", name="A"))
    v = SkillsView(repo)
    assert v.lista.count() == 1
    v.set_repo(None)
    assert v.lista.count() == 0
    assert v._skill_atual is None


def test_nova_cria_pasta_e_skill_md(qt_app, tmp_path):
    repo = SkillsRepo(tmp_path, bootstrap=False)
    v = SkillsView(repo)
    assert v.lista.count() == 0
    v._nova()
    assert v.lista.count() == 1
    arquivos = list((tmp_path / "skills").glob("*/SKILL.md"))
    assert len(arquivos) == 1


def test_duplicar_cria_segunda_skill(qt_app, tmp_path):
    repo = _repo(tmp_path, dict(
        slug="orig", name="Original", description="d",
        conteudo="# corpo\n", habilitada=True,
    ))
    v = SkillsView(repo)
    v.lista.setCurrentRow(0)
    v._duplicar()
    assert v.lista.count() == 2
    relidos = {s.slug: s for s in SkillsRepo(tmp_path, bootstrap=False).load()}
    assert "orig" in relidos
    copia = [s for s in relidos.values() if s.slug != "orig"][0]
    assert copia.habilitada is False


def test_excluir_remove_pasta(qt_app, tmp_path, monkeypatch):
    from PyQt6.QtWidgets import QMessageBox
    monkeypatch.setattr(
        QMessageBox, "question",
        staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes))
    repo = _repo(tmp_path, dict(slug="alvo", name="Alvo"))
    v = SkillsView(repo)
    v.lista.setCurrentRow(0)
    v._excluir()
    assert not (tmp_path / "skills" / "alvo").exists()
    assert v.lista.count() == 0
