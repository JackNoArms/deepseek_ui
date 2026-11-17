"""Testes do módulo de habilidades (``src/skills.py``) — padrão Agent Skills.

Cobrem: dataclass ``Skill``, parsing/serialização de frontmatter, CRUD no
repositório, ``set_habilitada`` sem tocar no ``SKILL.md``, filtro de
habilitadas e resiliência a arquivo corrompido.

A migração v1→v2 tem arquivo próprio (``test_skills_migration.py``).
"""

from pathlib import Path

from src.skills import (
    Skill,
    SkillsRepo,
    _join_frontmatter,
    _slugify,
    _split_frontmatter,
)


# ---- slug --------------------------------------------------------------

def test_slugify_simples():
    assert _slugify("Python Async") == "python-async"


def test_slugify_com_acentos():
    assert _slugify("Ação com Acentos") == "acao-com-acentos"
    assert _slugify("Game Dev — Godot") == "game-dev-godot"


def test_slugify_vazio():
    assert _slugify("") == ""
    assert _slugify("!!!") == ""


# ---- frontmatter -------------------------------------------------------

def test_split_frontmatter_ok():
    texto = "---\nname: X\ndescription: Y\n---\n# Corpo\n"
    meta, corpo = _split_frontmatter(texto)
    assert meta["name"] == "X"
    assert meta["description"] == "Y"
    assert corpo.strip() == "# Corpo"


def test_split_frontmatter_ausente():
    meta, corpo = _split_frontmatter("# só markdown\n")
    assert meta == {}
    assert corpo == "# só markdown\n"


def test_split_frontmatter_yaml_invalido():
    texto = "---\n: : :\n---\ncorpo\n"
    meta, corpo = _split_frontmatter(texto)
    assert meta == {}
    assert corpo == texto


def test_split_frontmatter_nao_fechado():
    texto = "---\nname: X\ncorpo sem fim"
    meta, corpo = _split_frontmatter(texto)
    assert meta == {}
    assert corpo == texto


def test_join_e_split_roundtrip():
    meta = {"name": "Nome: com dois pontos", "description": "Desc multi\nlinha"}
    texto = _join_frontmatter(meta)
    recuperado, _ = _split_frontmatter(texto + "\n# corpo")
    assert recuperado["name"] == meta["name"]
    assert recuperado["description"] == meta["description"]


# ---- load --------------------------------------------------------------

def test_load_vazio(tmp_path: Path):
    repo = SkillsRepo(tmp_path, bootstrap=False)
    assert repo.load() == []
    # skills/ pode nem existir ainda — o load não deve criar pasta vazia
    assert not (tmp_path / "skills").exists() or (tmp_path / "skills").is_dir()


def test_load_ignora_pasta_sem_skill_md(tmp_path: Path):
    pasta = tmp_path / "skills" / "vazia"
    pasta.mkdir(parents=True)
    repo = SkillsRepo(tmp_path, bootstrap=False)
    assert repo.load() == []


def test_ordem_estavel_por_slug(tmp_path: Path):
    repo = SkillsRepo(tmp_path, bootstrap=False)
    for slug in ("c", "a", "b"):
        repo.save(Skill(slug=slug, name=slug.upper()))
    repo.load()
    assert [s.slug for s in repo.all()] == ["a", "b", "c"]


# ---- save / load -------------------------------------------------------

def test_save_cria_skill_md(tmp_path: Path):
    repo = SkillsRepo(tmp_path, bootstrap=False)
    repo.save(Skill(
        slug="teste", name="Teste",
        description="desc de teste",
        conteudo="# Corpo\nlinha 2\n",
    ))

    arquivo = tmp_path / "skills" / "teste" / "SKILL.md"
    assert arquivo.exists()
    texto = arquivo.read_text(encoding="utf-8")
    assert texto.startswith("---\n")
    assert "name: Teste" in texto
    assert "description: desc de teste" in texto
    assert texto.rstrip().endswith("linha 2") or "linha 2" in texto


def test_save_e_load_roundtrip(tmp_path: Path):
    repo = SkillsRepo(tmp_path, bootstrap=False)
    repo.save(Skill(
        slug="round", name="Round",
        description="desc", habilitada=True,
        conteudo="# Header\n\ntexto\n",
    ))

    outro = SkillsRepo(tmp_path, bootstrap=False)
    lidas = outro.load()
    assert len(lidas) == 1
    s = lidas[0]
    assert s.slug == "round"
    assert s.name == "Round"
    assert s.description == "desc"
    assert s.habilitada is True
    assert "# Header" in s.conteudo


def test_save_cria_state_json(tmp_path: Path):
    repo = SkillsRepo(tmp_path, bootstrap=False)
    repo.save(Skill(slug="a", name="A", habilitada=True))
    state_path = tmp_path / ".deepseek_ui" / "skills_state.json"
    assert state_path.exists()


def test_save_multi_linha_description(tmp_path: Path):
    desc = "Linha 1.\nLinha 2 com dois pontos: e vírgula."
    repo = SkillsRepo(tmp_path, bootstrap=False)
    repo.save(Skill(slug="multi", name="Multi", description=desc))
    relido = SkillsRepo(tmp_path, bootstrap=False).load()[0]
    assert relido.description == desc


# ---- set_habilitada ----------------------------------------------------

def test_set_habilitada_persiste_no_state(tmp_path: Path):
    repo = SkillsRepo(tmp_path, bootstrap=False)
    repo.save(Skill(slug="a", name="A", habilitada=False))
    repo.load()
    s = repo.set_habilitada("a", True)
    assert s is not None and s.habilitada is True

    relido = SkillsRepo(tmp_path, bootstrap=False).load()[0]
    assert relido.habilitada is True


def test_set_habilitada_nao_toca_no_skill_md(tmp_path: Path):
    repo = SkillsRepo(tmp_path, bootstrap=False)
    repo.save(Skill(slug="a", name="A", habilitada=False, conteudo="# corpo\n"))
    caminho = tmp_path / "skills" / "a" / "SKILL.md"
    mtime_antes = caminho.stat().st_mtime_ns
    conteudo_antes = caminho.read_text(encoding="utf-8")

    repo.load()
    repo.set_habilitada("a", True)

    assert caminho.read_text(encoding="utf-8") == conteudo_antes
    assert caminho.stat().st_mtime_ns == mtime_antes


def test_set_habilitada_inexistente_devolve_none(tmp_path: Path):
    repo = SkillsRepo(tmp_path, bootstrap=False)
    repo.load()
    assert repo.set_habilitada("nao-existe", True) is None


# ---- delete ------------------------------------------------------------

def test_delete_remove_pasta_e_state(tmp_path: Path):
    repo = SkillsRepo(tmp_path, bootstrap=False)
    repo.save(Skill(slug="x", name="X"))
    repo.save(Skill(slug="y", name="Y"))
    repo.delete("x")

    assert not (tmp_path / "skills" / "x").exists()
    assert [s.slug for s in repo.all()] == ["y"]
    import json
    state = json.loads((tmp_path / ".deepseek_ui" / "skills_state.json").read_text(encoding="utf-8"))
    assert "x" not in state.get("skills", {})


def test_delete_inexistente_nao_explode(tmp_path: Path):
    repo = SkillsRepo(tmp_path, bootstrap=False)
    repo.load()
    repo.delete("nunca-existiu")


# ---- consulta ---------------------------------------------------------

def test_habilitadas_retorna_apenas_ligadas(tmp_path: Path):
    repo = SkillsRepo(tmp_path, bootstrap=False)
    repo.save(Skill(slug="on", name="On", habilitada=True))
    repo.save(Skill(slug="off", name="Off", habilitada=False))
    repo.load()
    slugs = [s.slug for s in repo.habilitadas()]
    assert slugs == ["on"]


def test_by_slug(tmp_path: Path):
    repo = SkillsRepo(tmp_path, bootstrap=False)
    repo.save(Skill(slug="alvo", name="Alvo"))
    assert repo.by_slug("alvo").name == "Alvo"
    assert repo.by_slug("nao-existe") is None


# ---- slug único --------------------------------------------------------

def test_novo_slug_sem_colisao(tmp_path: Path):
    repo = SkillsRepo(tmp_path, bootstrap=False)
    repo.load()
    assert repo.novo_slug("Nova Coisa") == "nova-coisa"


def test_novo_slug_com_colisao(tmp_path: Path):
    repo = SkillsRepo(tmp_path, bootstrap=False)
    repo.save(Skill(slug="game-dev", name="Game Dev"))
    assert repo.novo_slug("Game Dev") == "game-dev-2"
    repo.save(Skill(slug="game-dev-2", name="Game Dev 2"))
    assert repo.novo_slug("Game Dev") == "game-dev-3"


def test_novo_slug_vazio(tmp_path: Path):
    repo = SkillsRepo(tmp_path, bootstrap=False)
    repo.load()
    assert repo.novo_slug("!!!") == "skill"


# ---- resiliência -------------------------------------------------------

def test_arquivo_corrompido_nao_derruba(tmp_path: Path):
    pasta = tmp_path / "skills"
    (pasta / "quebrado").mkdir(parents=True)
    (pasta / "quebrado" / "SKILL.md").write_text(
        "---\n: : :\n---\ncorpo", encoding="utf-8")
    (pasta / "bom").mkdir(parents=True)
    (pasta / "bom" / "SKILL.md").write_text(
        "---\nname: Bom\ndescription: ok\n---\n# ok\n", encoding="utf-8")

    repo = SkillsRepo(tmp_path, bootstrap=False)
    lidas = repo.load()
    slugs = {s.slug for s in lidas}
    assert "bom" in slugs
    quebrado = repo.by_slug("quebrado")
    assert quebrado is not None
    # sem frontmatter válido: name cai para o slug
    assert quebrado.name == "quebrado"


def test_state_json_corrompido_nao_derruba(tmp_path: Path):
    repo = SkillsRepo(tmp_path, bootstrap=False)
    repo.save(Skill(slug="a", name="A", habilitada=True))
    state_path = tmp_path / ".deepseek_ui" / "skills_state.json"
    state_path.write_text("isto nao e json", encoding="utf-8")

    novo = SkillsRepo(tmp_path, bootstrap=False)
    lidas = novo.load()
    assert len(lidas) == 1
    assert lidas[0].slug == "a"
    # sem state válido, default é desabilitada
    assert lidas[0].habilitada is False
