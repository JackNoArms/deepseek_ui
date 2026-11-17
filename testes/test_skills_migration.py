"""Testes da migração v1→v2 (``skills/<slug>.md`` → ``skills/<slug>/SKILL.md``).

A migração roda dentro de ``SkillsRepo.load()`` de forma automática e
idempotente. Estes testes exercitam o comportamento de forma isolada,
montando o layout antigo manualmente em ``tmp_path``.
"""

import json
from pathlib import Path

from src.skills import SkillsRepo


def _v1_md(tmp_path: Path, slug: str, texto: str) -> Path:
    pasta = tmp_path / "skills"
    pasta.mkdir(exist_ok=True)
    caminho = pasta / f"{slug}.md"
    caminho.write_text(texto, encoding="utf-8")
    return caminho


def _state(tmp_path: Path) -> dict:
    p = tmp_path / ".deepseek_ui" / "skills_state.json"
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


# ---- conversão simples -------------------------------------------------

def test_migra_um_md_preserva_conteudo(tmp_path: Path):
    original = (
        "---\n"
        "nome: Minha Skill\n"
        "descricao: descrição curta da v1\n"
        "categoria: Jogos\n"
        "habilitada: true\n"
        "icone: \"🎮\"\n"
        "---\n"
        "# Corpo v1\n"
        "linha A\n"
        "linha B\n"
    )
    _v1_md(tmp_path, "minha-skill", original)

    repo = SkillsRepo(tmp_path, bootstrap=False)
    lidas = repo.load()

    assert len(lidas) == 1
    s = lidas[0]
    assert s.slug == "minha-skill"
    assert s.name == "Minha Skill"
    assert s.description == "descrição curta da v1"
    assert s.habilitada is True
    assert "# Corpo v1" in s.conteudo
    assert "linha A" in s.conteudo


def test_migra_move_md_antigo_para_backup(tmp_path: Path):
    caminho = _v1_md(tmp_path, "x", "---\nnome: X\n---\ncorpo\n")
    assert caminho.exists()

    SkillsRepo(tmp_path, bootstrap=False).load()

    assert not caminho.exists()
    backup = tmp_path / ".deepseek_ui" / "backups" / "skills-migration" / "x.md"
    assert backup.exists()
    assert "corpo" in backup.read_text(encoding="utf-8")


def test_migra_grava_state_com_habilitada(tmp_path: Path):
    _v1_md(tmp_path, "a", "---\nnome: A\nhabilitada: true\n---\ncorpo\n")
    _v1_md(tmp_path, "b", "---\nnome: B\nhabilitada: false\n---\ncorpo\n")

    SkillsRepo(tmp_path, bootstrap=False).load()

    state = _state(tmp_path)
    assert state["skills"]["a"]["habilitada"] is True
    assert state["skills"]["b"]["habilitada"] is False


def test_migra_multi_linha_description(tmp_path: Path):
    original = (
        "---\n"
        "nome: X\n"
        "descricao: >\n"
        "  Primeira linha.\n"
        "  Segunda linha.\n"
        "---\n"
        "corpo\n"
    )
    _v1_md(tmp_path, "x", original)

    lidas = SkillsRepo(tmp_path, bootstrap=False).load()
    assert "Primeira linha" in lidas[0].description
    assert "Segunda linha" in lidas[0].description


# ---- idempotência ------------------------------------------------------

def test_migra_duas_vezes_nao_duplica(tmp_path: Path):
    _v1_md(tmp_path, "x", "---\nnome: X\nhabilitada: true\n---\ncorpo\n")

    SkillsRepo(tmp_path, bootstrap=False).load()
    SkillsRepo(tmp_path, bootstrap=False).load()

    state = _state(tmp_path)
    assert list(state["skills"].keys()) == ["x"]
    backups = list((tmp_path / ".deepseek_ui" / "backups" / "skills-migration").glob("*.md"))
    assert len(backups) == 1


def test_migra_nao_sobrescreve_state_existente(tmp_path: Path):
    _v1_md(tmp_path, "x", "---\nnome: X\nhabilitada: false\n---\ncorpo\n")
    # Simula usuário que já desligou a skill manualmente no v2
    state_dir = tmp_path / ".deepseek_ui"
    state_dir.mkdir()
    (state_dir / "skills_state.json").write_text(
        json.dumps({"version": 1, "skills": {"x": {"habilitada": True}}}),
        encoding="utf-8",
    )

    SkillsRepo(tmp_path, bootstrap=False).load()

    state = _state(tmp_path)
    # state existente venceu — habilitada continua true
    assert state["skills"]["x"]["habilitada"] is True


def test_migra_preserva_skill_md_existente(tmp_path: Path):
    # Simula situação onde já existe <slug>/SKILL.md e também um <slug>.md antigo
    pasta = tmp_path / "skills" / "x"
    pasta.mkdir(parents=True)
    (pasta / "SKILL.md").write_text(
        "---\nname: X v2\ndescription: já migrado\n---\ncorpo v2\n",
        encoding="utf-8",
    )
    _v1_md(tmp_path, "x", "---\nnome: X velho\n---\ncorpo v1\n")

    repo = SkillsRepo(tmp_path, bootstrap=False)
    lidas = repo.load()

    assert len(lidas) == 1
    assert lidas[0].name == "X v2"
    # SKILL.md intacto
    skill_md = (pasta / "SKILL.md").read_text(encoding="utf-8")
    assert "X v2" in skill_md
    # .md antigo foi para backup
    backup = tmp_path / ".deepseek_ui" / "backups" / "skills-migration" / "x.md"
    assert backup.exists()


# ---- sem migração necessária -------------------------------------------

def test_sem_legado_nao_cria_backup_dir(tmp_path: Path):
    repo = SkillsRepo(tmp_path, bootstrap=False)
    repo.load()
    assert not (tmp_path / ".deepseek_ui" / "backups" / "skills-migration").exists()


def test_so_pastas_v2_nao_dispara_migracao(tmp_path: Path):
    # Cria uma skill v2 direto pelo repo
    from src.skills import Skill
    repo = SkillsRepo(tmp_path, bootstrap=False)
    repo.save(Skill(slug="a", name="A", conteudo="# corpo\n"))

    # Não deve haver nenhum .md solto em skills/
    assert list((tmp_path / "skills").glob("*.md")) == []


# ---- casos de borda ----------------------------------------------------

def test_migra_md_sem_frontmatter(tmp_path: Path):
    _v1_md(tmp_path, "solto", "# Apenas markdown\n\nconteúdo\n")

    lidas = SkillsRepo(tmp_path, bootstrap=False).load()
    assert len(lidas) == 1
    assert lidas[0].slug == "solto"
    assert lidas[0].name == "solto"
    assert lidas[0].description == ""
    assert lidas[0].habilitada is False
    assert "# Apenas markdown" in lidas[0].conteudo


def test_migra_preserva_corpo_com_crases(tmp_path: Path):
    original = (
        "---\n"
        "nome: X\n"
        "---\n"
        "# Header\n"
        "\n"
        "```python\n"
        "def f():\n"
        "    return 42\n"
        "```\n"
    )
    _v1_md(tmp_path, "x", original)

    lidas = SkillsRepo(tmp_path, bootstrap=False).load()
    assert "```python" in lidas[0].conteudo
    assert "return 42" in lidas[0].conteudo
