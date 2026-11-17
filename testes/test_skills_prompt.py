"""Testes do `bloco_habilidades` em `src/prompts.py` (padrão Agent Skills).

Cobrem: bloco vazio, só habilitadas dentro do limite, só desabilitadas,
habilitadas excedentes, instrução de portões 🛑, instrução de levantamento,
integração com `montar` (ordem pedido→contexto, ausência quando None).
"""

from types import SimpleNamespace

from src.prompts import LIMITE_SKILLS_POR_TURNO, bloco_habilidades, montar


def _skill(slug, habilitada=False, name=None, description="", conteudo=""):
    return SimpleNamespace(
        slug=slug,
        name=name or slug,
        description=description,
        conteudo=conteudo,
        habilitada=habilitada,
    )


# ---- bloco_habilidades -------------------------------------------------

def test_bloco_vazio_retorna_string_vazia():
    assert bloco_habilidades([]) == ""
    assert bloco_habilidades(None) == ""


def test_bloco_so_habilitadas_dentro_do_limite():
    skills = [_skill("alpha", True, conteudo="## Alpha\nconteudo A")]
    bloco = bloco_habilidades(skills)
    assert "## Habilidades habilitadas (conteúdo completo)" in bloco
    assert "### alpha" in bloco
    assert "conteudo A" in bloco
    assert "Outras habilidades" not in bloco


def test_bloco_so_desabilitadas():
    skills = [_skill("beta", False, description="desc de beta")]
    bloco = bloco_habilidades(skills)
    assert "## Habilidades habilitadas" not in bloco
    assert "## Outras habilidades disponíveis" in bloco
    assert "**beta**" in bloco
    assert "desc de beta" in bloco


def test_bloco_misto_habilitada_e_desabilitada():
    skills = [
        _skill("on", True, description="on desc", conteudo="conteudo on"),
        _skill("off", False, description="off desc"),
    ]
    bloco = bloco_habilidades(skills)
    assert "### on" in bloco
    assert "conteudo on" in bloco
    assert "**off**" in bloco
    assert "off desc" in bloco


def test_bloco_inclui_instrucao_de_portoes():
    skills = [_skill("on", True, conteudo="# corpo")]
    bloco = bloco_habilidades(skills)
    assert "## Portões" in bloco
    assert "decision" in bloco


def test_bloco_inclui_instrucao_de_levantamento():
    skills = [_skill("off", False)]
    bloco = bloco_habilidades(skills)
    assert "levantamento" in bloco.lower()


def test_bloco_habilitada_sem_conteudo():
    skills = [_skill("vazia", True, conteudo="")]
    bloco = bloco_habilidades(skills)
    assert "### vazia" in bloco
    assert "_(sem conteúdo)_" in bloco


# ---- limite de skills por turno ----------------------------------------

def test_bloco_corta_habilitadas_acima_do_limite():
    skills = [
        _skill("a", True, conteudo="corpo A"),
        _skill("b", True, conteudo="corpo B"),
        _skill("c", True, conteudo="corpo C"),
    ]
    bloco = bloco_habilidades(skills)
    # a e b são as duas primeiras por slug; c fica de fora
    assert "corpo A" in bloco
    assert "corpo B" in bloco
    assert "corpo C" not in bloco
    # c aparece no índice com aviso
    assert "**c**" in bloco
    assert "fora do limite" in bloco


def test_bloco_respeita_ordem_alfabetica_por_slug():
    skills = [
        _skill("zeta", True, conteudo="conteudo zeta"),
        _skill("alpha", True, conteudo="conteudo alpha"),
        _skill("meio", True, conteudo="conteudo meio"),
    ]
    bloco = bloco_habilidades(skills)
    # alpha e meio são as duas primeiras; zeta fica fora
    assert "conteudo alpha" in bloco
    assert "conteudo meio" in bloco
    assert "conteudo zeta" not in bloco


def test_bloco_limite_customizado():
    skills = [
        _skill("a", True, conteudo="corpo A"),
        _skill("b", True, conteudo="corpo B"),
    ]
    bloco = bloco_habilidades(skills, limite=1)
    assert "corpo A" in bloco
    assert "corpo B" not in bloco
    assert "**b**" in bloco


def test_limite_padrao_e_2():
    assert LIMITE_SKILLS_POR_TURNO == 2


# ---- description longa é truncada no índice ----------------------------

def test_bloco_trunca_description_longa_no_indice():
    desc_gigante = "palavra " * 200
    skills = [_skill("x", False, description=desc_gigante)]
    bloco = bloco_habilidades(skills)
    # não explode de tamanho; contém reticências
    assert "…" in bloco


# ---- integração com montar --------------------------------------------

def test_montar_sem_habilidades_nao_injeta():
    out = montar("faz X")
    assert "HABILIDADES" not in out


def test_montar_com_habilidades_injeta():
    skills = [_skill("minha", True, name="Minha", conteudo="instruções da skill")]
    out = montar("faz X", habilidades=skills)
    assert "HABILIDADES" in out
    assert "Minha" in out
    assert "instruções da skill" in out


def test_montar_habilidades_apos_pedido():
    skills = [_skill("minha", True, conteudo="conteudo")]
    out = montar("pedido do usuario X", habilidades=skills)
    assert out.index("pedido do usuario X") < out.index("HABILIDADES")


def test_montar_habilidades_apos_instrucoes():
    skills = [_skill("minha", True, conteudo="conteudo")]
    out = montar("pedido", habilidades=skills, instrucoes="regras do AGENTS")
    assert out.index("regras do AGENTS") < out.index("HABILIDADES")


def test_montar_habilidades_vazias_nao_injeta():
    out = montar("pedido", habilidades=[])
    assert "HABILIDADES" not in out
