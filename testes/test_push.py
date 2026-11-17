"""Prova do módulo Web Push: chave VAPID, inscrições e entrega.

A entrega real (o POST HTTPS para Mozilla/Google/Apple) é mockada: testar a
`pywebpush` não prova nada do nosso código. O que está sob teste aqui é a
camada nossa — geração/persistência de chave, validação de inscrição, limpeza
de endpoint morto.
"""

import base64
import json

import pytest

from src import push as push_mod
from src.push import PushManager


@pytest.fixture
def gerenciador(tmp_path, monkeypatch):
    """Um PushManager isolado, com `webpush` desligado por padrão.

    Testes que exercitam `notificar` sobrescrevem `push_mod.webpush` com um
    fake próprio. Os que só exercitam chave/inscrição ficam com `None` e não
    fazem chamada de rede por acidente.
    """
    monkeypatch.setattr(push_mod, "webpush", None)
    return PushManager(pasta_estado=tmp_path)


class _RespostaFalsa:
    def __init__(self, status_code=201):
        self.status_code = status_code


class _ErroPush(push_mod.WebPushException):
    """WebPushException com a forma que `notificar` inspeciona."""

    def __init__(self, status_code):
        super().__init__("erro simulado")
        self.response = _RespostaFalsa(status_code)


# ---------------- chaves ----------------


def test_chave_vapid_gerada_e_persistida(tmp_path):
    a = PushManager(pasta_estado=tmp_path)
    assert (tmp_path / "vapid_private.pem").is_file()
    b = PushManager(pasta_estado=tmp_path)
    assert a.public_key() == b.public_key()


def test_chave_publica_e_ponto_ec_uncompressed(tmp_path):
    g = PushManager(pasta_estado=tmp_path)
    b64 = g.public_key()
    # Sem padding, como o navegador exige em applicationServerKey.
    assert "=" not in b64
    bruto = base64.urlsafe_b64decode(b64 + "=" * (-len(b64) % 4))
    assert len(bruto) == 65
    assert bruto[0] == 0x04  # prefixo de ponto uncompressed do SEC1


# ---------------- inscrições ----------------


def test_inscricao_roundtrip(gerenciador, tmp_path):
    assert not gerenciador.tem_inscricoes()
    ok = gerenciador.subscribe({
        "endpoint": "https://example.test/push/1",
        "keys": {"p256dh": "abc", "auth": "def"},
    })
    assert ok
    assert gerenciador.tem_inscricoes()
    inscricoes = gerenciador.listar()
    assert len(inscricoes) == 1
    assert inscricoes[0]["endpoint"] == "https://example.test/push/1"
    # Ficou salvo em disco (nova instância lê o mesmo arquivo).
    outra = PushManager(pasta_estado=tmp_path)
    assert outra.tem_inscricoes()


def test_inscricao_malformada_e_recusada(gerenciador):
    assert not gerenciador.subscribe({})
    assert not gerenciador.subscribe({"endpoint": ""})
    assert not gerenciador.subscribe({"endpoint": "x"})
    assert not gerenciador.subscribe({"endpoint": "x", "keys": {}})
    assert not gerenciador.subscribe(
        {"endpoint": "x", "keys": {"p256dh": "p"}})
    assert not gerenciador.tem_inscricoes()


def test_inscricao_repetida_atualiza_em_vez_de_duplicar(gerenciador):
    gerenciador.subscribe({
        "endpoint": "https://e/1",
        "keys": {"p256dh": "v1", "auth": "a1"},
    })
    gerenciador.subscribe({
        "endpoint": "https://e/1",
        "keys": {"p256dh": "v2", "auth": "a2"},
    })
    inscricoes = gerenciador.listar()
    assert len(inscricoes) == 1
    assert inscricoes[0]["keys"]["p256dh"] == "v2"


def test_unsubscribe_remove(gerenciador):
    gerenciador.subscribe({
        "endpoint": "https://e/1",
        "keys": {"p256dh": "p", "auth": "a"},
    })
    assert gerenciador.unsubscribe("https://e/1")
    assert not gerenciador.tem_inscricoes()
    # Remover de novo é no-op.
    assert not gerenciador.unsubscribe("https://e/1")


# ---------------- entrega ----------------


def test_notificar_entrega_payload(gerenciador, monkeypatch):
    chamadas = []

    def falso_webpush(**kwargs):
        chamadas.append(kwargs)
        return _RespostaFalsa(201)

    monkeypatch.setattr(push_mod, "webpush", falso_webpush)
    gerenciador.subscribe({
        "endpoint": "https://e/1",
        "keys": {"p256dh": "p", "auth": "a"},
    })
    gerenciador.subscribe({
        "endpoint": "https://e/2",
        "keys": {"p256dh": "p", "auth": "a"},
    })
    entregues = gerenciador.notificar("Decisão necessária", "Escolher A ou B",
                                       "/?d=abc")
    assert entregues == 2
    assert len(chamadas) == 2
    payload = json.loads(chamadas[0]["data"])
    assert payload["title"] == "Decisão necessária"
    assert payload["body"] == "Escolher A ou B"
    assert payload["url"] == "/?d=abc"
    # VAPID sub é obrigatório no JWT.
    assert chamadas[0]["vapid_claims"]["sub"].startswith("mailto:")


def test_notificar_remove_inscricoes_expiradas(gerenciador, monkeypatch):
    def falso_webpush(**kwargs):
        endpoint = kwargs["subscription_info"]["endpoint"]
        if endpoint.endswith("/morto"):
            raise _ErroPush(410)
        return _RespostaFalsa(201)

    monkeypatch.setattr(push_mod, "webpush", falso_webpush)
    gerenciador.subscribe({
        "endpoint": "https://e/vivo",
        "keys": {"p256dh": "p", "auth": "a"},
    })
    gerenciador.subscribe({
        "endpoint": "https://e/morto",
        "keys": {"p256dh": "p", "auth": "a"},
    })
    entregues = gerenciador.notificar("T", "C")
    assert entregues == 1
    restantes = {s["endpoint"] for s in gerenciador.listar()}
    assert restantes == {"https://e/vivo"}


def test_notificar_sem_inscricoes_nao_chama_webpush(gerenciador, monkeypatch):
    chamadas = []

    def falso_webpush(**kwargs):
        chamadas.append(kwargs)

    monkeypatch.setattr(push_mod, "webpush", falso_webpush)
    assert gerenciador.notificar("T", "C") == 0
    assert chamadas == []


def test_notificar_sem_webpush_nao_falha(gerenciador):
    # `webpush` já está None via fixture; nada deve explodir.
    assert gerenciador.notificar("T", "C") == 0
