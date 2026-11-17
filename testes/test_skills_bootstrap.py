"""Testes do bootstrap de skills padrão (``assets/skills_default/``).

Cobrem: projeto vazio recebe os defaults, skill existente não é sobrescrita,
skill apagada não é ressuscitada, idempotência, ``habilitada`` começa False,
``defaults_dir=None`` desativa o bootstrap, e defaults com ``SKILL.md``
ausente/corrompido são ignorados sem explodir.
"""

import json
from pathlib import Path

from src.skills import SkillsRepo


def _fazer_default(defaults_dir: Path, slug: str, name: str,
                   description: str = "", conteudo: str = "# corpo\n") -> Path:
    """Cria `<defaults>/<slug>/SKILL.md` e devolve o caminho."""
    pasta = defaults_dir / slug
    pasta.mkdir(parents=True, exist_ok=True)
    texto = (
        f"---\nname: {name}\ndescription: {description}\n---\n\n{conteudo}"
    )
    caminho = pasta / "SKILL.md"
    caminho.write_text(texto, encoding="utf-8")
    return caminho


def _state(tmp_path: Path) -> dict:
    p = tmp_path / ".deepseek_ui" / "skills_state.json"
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


# ---- desativado -------------------------------------------------------

def test_sem_defaults_dir_nao_faz_nada(tmp_path):
    repo = SkillsRepo(tmp_path, bootstrap=False)
    assert repo.load() == []
    # sem state file — bootstrap desativado não mexe
    assert not (tmp_path / ".deepseek_ui" / "skills_state.json").exists()


def test_defaults_dir_inexistente_e_ignorado(tmp_path):
    padrao = tmp_path / "nao_existe" / "skills_default"
    repo = SkillsRepo(tmp_path, defaults_dir=padrao)
    assert repo.load() == []
    # sem state, sem skills
    assert not (tmp_path / "skills").exists()


# ---- bootstrap básico -------------------------------------------------

def test_bootstrap_projeto_vazio_copia_defaults(tmp_path):
    defaults = tmp_path / "defaults"
    _fazer_default(defaults, "backend-dev", "backend-dev", "d1")
    _fazer_default(defaults, "frontend-ui", "frontend-ui", "d2")

    projeto = tmp_path / "projeto"
    projeto.mkdir()
    repo = SkillsRepo(projeto, defaults_dir=defaults)
    skills = repo.load()

    assert len(skills) == 2
    slugs = {s.slug for s in skills}
    assert slugs == {"backend-dev", "frontend-ui"}
    # SKILL.md foi criado em disco
    assert (projeto / "skills" / "backend-dev" / "SKILL.md").is_file()
    assert (projeto / "skills" / "frontend-ui" / "SKILL.md").is_file()
    # defaults_aplicados marcou os dois
    state = _state(projeto)
    assert set(state["defaults_aplicados"]) == {"backend-dev", "frontend-ui"}


def test_bootstrap_nao_sobrescreve_skill_existente(tmp_path):
    defaults = tmp_path / "defaults"
    _fazer_default(defaults, "backend-dev", "backend-dev v-folha",
                   "desc padrao")

    projeto = tmp_path / "projeto"
    pasta = projeto / "skills" / "backend-dev"
    pasta.mkdir(parents=True)
    (pasta / "SKILL.md").write_text(
        "---\nname: customizado\ndescription: desc customizada\n---\n# custom\n",
        encoding="utf-8",
    )

    repo = SkillsRepo(projeto, defaults_dir=defaults)
    skills = repo.load()

    assert len(skills) == 1
    assert skills[0].name == "customizado"
    # não sobrescreveu o SKILL.md existente
    texto = (pasta / "SKILL.md").read_text(encoding="utf-8")
    assert "customizado" in texto
    assert "v-folha" not in texto


# ---- ressuscitação ----------------------------------------------------

def test_bootstrap_nao_ressuscita_skill_apagada(tmp_path):
    defaults = tmp_path / "defaults"
    _fazer_default(defaults, "backend-dev", "backend-dev")

    projeto = tmp_path / "projeto"
    projeto.mkdir()
    repo1 = SkillsRepo(projeto, defaults_dir=defaults)
    repo1.load()
    assert (projeto / "skills" / "backend-dev").is_dir()

    repo1.delete("backend-dev")
    assert not (projeto / "skills" / "backend-dev").exists()

    # nova instância, mesmo defaults_dir → não deve ressuscitar
    repo2 = SkillsRepo(projeto, defaults_dir=defaults)
    skills = repo2.load()
    assert skills == []
    assert not (projeto / "skills" / "backend-dev").exists()


# ---- idempotência -----------------------------------------------------

def test_bootstrap_idempotente(tmp_path):
    defaults = tmp_path / "defaults"
    _fazer_default(defaults, "a", "A")
    _fazer_default(defaults, "b", "B")

    projeto = tmp_path / "projeto"
    projeto.mkdir()
    repo = SkillsRepo(projeto, defaults_dir=defaults)
    repo.load()
    repo.load()
    repo.load()

    state = _state(projeto)
    assert sorted(state["defaults_aplicados"]) == ["a", "b"]
    assert len(list((projeto / "skills").glob("*/SKILL.md"))) == 2


# ---- habilitada -------------------------------------------------------

def test_bootstrap_nao_mexe_em_habilitada(tmp_path):
    defaults = tmp_path / "defaults"
    _fazer_default(defaults, "backend-dev", "backend-dev")

    projeto = tmp_path / "projeto"
    projeto.mkdir()
    repo = SkillsRepo(projeto, defaults_dir=defaults)
    skills = repo.load()

    assert skills[0].habilitada is False
    # state não tem entrada de habilitada (ou tem, mas False)
    state = _state(projeto)
    if "backend-dev" in state.get("skills", {}):
        assert state["skills"]["backend-dev"]["habilitada"] is False


# ---- resiliência ------------------------------------------------------

def test_default_sem_skill_md_e_ignorado(tmp_path):
    defaults = tmp_path / "defaults"
    # Pasta vazia (sem SKILL.md)
    (defaults / "vazia").mkdir(parents=True)
    _fazer_default(defaults, "boa", "Boa")

    projeto = tmp_path / "projeto"
    projeto.mkdir()
    repo = SkillsRepo(projeto, defaults_dir=defaults)
    skills = repo.load()

    assert len(skills) == 1
    assert skills[0].slug == "boa"
    # Ambos foram marcados — o vazio também (não reavalia na próxima carga)
    state = _state(projeto)
    assert "vazia" in state["defaults_aplicados"]
    assert "boa" in state["defaults_aplicados"]


# ---- coexistência com migração ---------------------------------------

def test_bootstrap_apos_migracao_preserva_conteudo(tmp_path):
    """Se o usuário tinha v1 ``skills/<slug>.md``, migração roda antes do
    bootstrap — o conteúdo do usuário fica, o default não copia por cima.
    """
    defaults = tmp_path / "defaults"
    _fazer_default(defaults, "backend-dev", "backend-dev v-folha",
                   "desc padrao")

    projeto = tmp_path / "projeto"
    pasta = projeto / "skills"
    pasta.mkdir(parents=True)
    (pasta / "backend-dev.md").write_text(
        "---\nnome: Meu backend\ndescricao: desc do usuario\nhabilitada: true\n---\n"
        "# conteudo do usuario\n",
        encoding="utf-8",
    )

    repo = SkillsRepo(projeto, defaults_dir=defaults)
    skills = repo.load()

    assert len(skills) == 1
    assert skills[0].name == "Meu backend"
    assert skills[0].habilitada is True
    assert "conteudo do usuario" in skills[0].conteudo
