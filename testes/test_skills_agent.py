"""Testes do contrato entre ``Agente`` e o bloco de habilidades.

Não testa o loop inteiro: usa um controller fake e intercepta ``montar``
para capturar os kwargs. Foco em três coisas:

- ``_resolver_habilidades`` aceita ``None``, lista, callable e objeto ``.all()``.
- ``montar`` recebe ``habilidades`` resolvido (lista).
- Quando não há habilidades, o kwarg chega como ``None``.

O ``_Skill`` fake reflete a dataclass nova do padrão Agent Skills, mas
os testes não dependem de campos específicos — só de identidade e passagem.
"""

import pytest

from src.agent import Agente, Callbacks


class _Skill:
    def __init__(self, name="X"):
        self.slug = name.lower()
        self.name = name
        self.description = ""
        self.conteudo = ""
        self.habilitada = True


class _Repo:
    def __init__(self, skills):
        self._skills = skills

    def all(self):
        return list(self._skills)


class _Controller:
    def send_message(self, *a, **k):  # pragma: no cover - não chamado nos testes
        return ""


class _Parar(Exception):
    """Sentinela: interrompe ``Agente.rodar`` logo depois de ``montar``."""


# ---- _resolver_habilidades ---------------------------------------------

def test_resolver_none():
    ag = Agente(_Controller(), None, Callbacks())
    assert ag._resolver_habilidades() is None


def test_resolver_lista():
    s = _Skill("A")
    ag = Agente(_Controller(), None, Callbacks(), habilidades=[s])
    assert ag._resolver_habilidades() == [s]


def test_resolver_repo_com_all():
    s = _Skill("B")
    ag = Agente(_Controller(), None, Callbacks(), habilidades=_Repo([s]))
    assert ag._resolver_habilidades() == [s]


def test_resolver_callable():
    s = _Skill("C")
    chamado = {"n": 0}

    def provider():
        chamado["n"] += 1
        return [s]

    ag = Agente(_Controller(), None, Callbacks(), habilidades=provider)
    assert ag._resolver_habilidades() == [s]
    assert chamado["n"] == 1


# ---- Integração com montar ---------------------------------------------

def _capturar_montar(monkeypatch):
    capturado = {}

    def fake_montar(pedido, **kwargs):
        capturado["pedido"] = pedido
        capturado.update(kwargs)
        raise _Parar()

    monkeypatch.setattr("src.agent.montar", fake_montar)
    return capturado


def test_agente_passa_habilidades_para_montar(monkeypatch):
    capturado = _capturar_montar(monkeypatch)
    s = _Skill("X")
    ag = Agente(_Controller(), None, Callbacks(), habilidades=[s])
    with pytest.raises(_Parar):
        ag.rodar("pedido")
    assert capturado["habilidades"] == [s]
    assert capturado["pedido"] == "pedido"


def test_agente_passa_none_quando_sem_habilidades(monkeypatch):
    capturado = _capturar_montar(monkeypatch)
    ag = Agente(_Controller(), None, Callbacks())
    with pytest.raises(_Parar):
        ag.rodar("pedido")
    assert capturado["habilidades"] is None


def test_agente_repo_resolve_no_momento_do_rodar(monkeypatch):
    """Se o repo mudar entre dois ``rodar``, o segundo vê o estado novo."""
    s1, s2 = _Skill("S1"), _Skill("S2")
    repo = _Repo([s1])
    capturado = _capturar_montar(monkeypatch)
    ag = Agente(_Controller(), None, Callbacks(), habilidades=repo)

    with pytest.raises(_Parar):
        ag.rodar("primeiro")
    assert capturado["habilidades"] == [s1]

    repo._skills = [s1, s2]
    with pytest.raises(_Parar):
        ag.rodar("segundo")
    assert capturado["habilidades"] == [s1, s2]
