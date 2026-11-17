"""Prova do painel remoto: token, estado, decisão, push e PWA.

Sobe o servidor em porta efêmera (porta=0) para não brigar com o app de
verdade nem com outras execuções do pytest. Não abre o Tailscale — o que
está sendo testado é o contrato HTTP que o `tailscale serve` vai encaminhar.

Os testes de push mockam `PushManager.notificar`: o POST HTTPS para o
serviço de push real é da `pywebpush`, não nosso. O que se prova aqui é que
o painel chama a notificação quando e como deve.

**Qt.** A `QApplication` é criada em `conftest.pytest_sessionstart` — nunca
`QCoreApplication` aqui, porque criá-la primeiro impede `QApplication` no
mesmo processo (`STATUS_STACK_BUFFER_OVERRUN` em Python 3.14 + PyQt6). A
fixture `qcore` reaproveita a instância já existente.
"""

import http.client
import json
import time

import pytest
from PyQt6.QtWidgets import QApplication

from src.remote import RemoteServer

# Guarda a referência: sem isso, o Python coleta o QApplication e o PyQt
# pode reclamar ao criar QObject em testes seguintes.
_APP = None


@pytest.fixture(scope="module", autouse=True)
def qcore():
    global _APP
    _APP = QApplication.instance() or QApplication([])
    yield


class _PushFake:
    """PushManager de mentira: registra chamadas e finge ter inscrições."""

    def __init__(self, tem: bool = True):
        self._tem = tem
        self.chamadas: list[tuple[str, str, str]] = []
        self.public_key_retorno = "chave-publica-falsa"

    def tem_inscricoes(self):
        return self._tem

    def public_key(self):
        return self.public_key_retorno

    def subscribe(self, inscricao):
        endpoint = (inscricao or {}).get("endpoint")
        chaves = (inscricao or {}).get("keys")
        return bool(endpoint and isinstance(chaves, dict)
                    and chaves.get("p256dh") and chaves.get("auth"))

    def unsubscribe(self, endpoint):
        return endpoint == "https://existe/1"

    def notificar(self, titulo, corpo="", url="/"):
        self.chamadas.append((titulo, corpo, url))
        return 1


@pytest.fixture
def servidor(tmp_path):
    push = _PushFake(tem=True)
    server = RemoteServer(porta=0, token_path=str(tmp_path / "token"), push=push)
    server.start()
    server._push_fake = push  # conveniência de teste
    yield server
    server.stop()


def _get(porta, caminho, token=None):
    con = http.client.HTTPConnection("127.0.0.1", porta, timeout=3)
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    con.request("GET", caminho, headers=headers)
    r = con.getresponse()
    corpo = r.read()
    cabecalhos = dict(r.getheaders())
    con.close()
    return r.status, corpo, cabecalhos


def _post(porta, caminho, token, payload):
    con = http.client.HTTPConnection("127.0.0.1", porta, timeout=3)
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    con.request("POST", caminho, body=json.dumps(payload), headers=headers)
    r = con.getresponse()
    corpo = r.read()
    con.close()
    return r.status, corpo


class _AcaoFalsa:
    """Ação de decisão mínima: só o `extras` que o card do chat entrega."""

    def __init__(self, pergunta, opcoes, recomendada=None, motivo=None):
        self.extras = {
            "pergunta": pergunta,
            "opcoes": opcoes,
            "recomendada": recomendada,
            "motivo": motivo,
        }


# ---------------- auth e estado ----------------


def test_sem_token_e_recusado(servidor):
    status, _, _ = _get(servidor.porta, "/api/state")
    assert status == 401


def test_token_errado_e_recusado(servidor):
    status, _, _ = _get(servidor.porta, "/api/state", token="nao-e-o-token")
    assert status == 401


def test_estado_com_token(servidor):
    servidor.update(status="conectado", status_tone="success", connected=True)
    status, corpo, _ = _get(servidor.porta, "/api/state", token=servidor.token)
    assert status == 200
    dados = json.loads(corpo)
    assert dados["status"] == "conectado"
    assert dados["status_tone"] == "success"
    assert dados["connected"] is True
    assert dados["pending_decisions"] == []


# ---------------- estáticos (PWA) ----------------


def test_service_worker_servido_sem_token(servidor):
    status, corpo, cabecalhos = _get(servidor.porta, "/sw.js")
    assert status == 200
    assert cabecalhos.get("Content-Type", "").startswith("application/javascript")
    texto = corpo.decode("utf-8")
    assert "addEventListener('push'" in texto
    assert "notificationclick" in texto


def test_manifest_servido_sem_token(servidor):
    status, corpo, cabecalhos = _get(servidor.porta, "/manifest.webmanifest")
    assert status == 200
    assert cabecalhos.get("Content-Type", "").startswith("application/manifest+json")
    m = json.loads(corpo)
    assert m["display"] == "standalone"
    assert m["start_url"] == "/"
    assert any(i["sizes"] == "192x192" for i in m["icons"])


def test_icone_png_valido(servidor):
    status, corpo, cabecalhos = _get(servidor.porta, "/icon-192.png")
    assert status == 200
    assert cabecalhos.get("Content-Type") == "image/png"
    # Assinatura do PNG.
    assert corpo.startswith(b"\x89PNG\r\n\x1a\n")
    # Tamanho declarado no IHDR (offsets 16..23).
    largura, altura = int.from_bytes(corpo[16:20], "big"), int.from_bytes(corpo[20:24], "big")
    assert (largura, altura) == (192, 192)


# ---------------- VAPID e inscrição ----------------


def test_vapid_public_key_requer_token(servidor):
    status, _, _ = _get(servidor.porta, "/api/vapid-public-key")
    assert status == 401


def test_vapid_public_key_devolve_chave(servidor):
    status, corpo, _ = _get(
        servidor.porta, "/api/vapid-public-key", token=servidor.token)
    assert status == 200
    dados = json.loads(corpo)
    assert dados["key"] == "chave-publica-falsa"


def test_subscribe_valido(servidor):
    status, _ = _post(
        servidor.porta, "/api/subscribe", servidor.token,
        {"endpoint": "https://e/1", "keys": {"p256dh": "p", "auth": "a"}})
    assert status == 200


def test_subscribe_malformado_e_recusado(servidor):
    status, _ = _post(
        servidor.porta, "/api/subscribe", servidor.token, {"endpoint": ""})
    assert status == 400


def test_unsubscribe_delega_ao_push(servidor):
    status, corpo = _post(
        servidor.porta, "/api/unsubscribe", servidor.token,
        {"endpoint": "https://existe/1"})
    assert status == 200
    assert json.loads(corpo)["ok"] is True


def test_unsubscribe_sem_endpoint_e_recusado(servidor):
    status, _ = _post(servidor.porta, "/api/unsubscribe", servidor.token, {})
    assert status == 400


# ---------------- decisões ----------------


def test_decisao_publicada_aparece_no_estado(servidor):
    acao = _AcaoFalsa("Mudar a cor do botão?", ["Sim", "Não"],
                      recomendada=2, motivo="Não quebra nada")
    id_card = servidor.publish_decision(acao)
    _, corpo, _ = _get(servidor.porta, "/api/state", token=servidor.token)
    dados = json.loads(corpo)
    pendentes = dados["pending_decisions"]
    assert len(pendentes) == 1
    d = pendentes[0]
    assert d["id"] == id_card
    assert d["pergunta"] == "Mudar a cor do botão?"
    assert d["opcoes"] == ["Sim", "Não"]
    assert d["recomendada"] == 2
    assert d["motivo"] == "Não quebra nada"


def test_decisao_dispara_notificacao_em_thread(servidor):
    acao = _AcaoFalsa("A ou B?", ["A", "B"])
    servidor.publish_decision(acao)
    # A notificação roda numa thread; dá um tempo curto para ela ser chamada.
    limite = time.monotonic() + 2.0
    while not servidor._push_fake.chamadas and time.monotonic() < limite:
        time.sleep(0.02)
    assert servidor._push_fake.chamadas
    titulo, corpo, url = servidor._push_fake.chamadas[0]
    assert titulo == "Decisão necessária"
    assert corpo == "A ou B?"
    assert url == "/"


def test_notificacao_nao_e_disparada_sem_inscricoes(tmp_path):
    push = _PushFake(tem=False)
    server = RemoteServer(porta=0, token_path=str(tmp_path / "t"), push=push)
    server.start()
    try:
        server.publish_decision(_AcaoFalsa("X?", ["S", "N"]))
        time.sleep(0.15)
        assert push.chamadas == []
    finally:
        server.stop()


def test_resposta_a_decisao_via_http(servidor):
    acao = _AcaoFalsa("Escolher A ou B?", ["A", "B"])
    id_card = servidor.publish_decision(acao)
    status, _ = _post(
        servidor.porta, f"/api/decision/{id_card}", servidor.token,
        {"escolha": "A"})
    assert status == 200

    # Repetir a resposta é recusado: a decisão já foi tomada.
    status2, _ = _post(
        servidor.porta, f"/api/decision/{id_card}", servidor.token,
        {"escolha": "B"})
    assert status2 == 409

    # E sumiu da lista de pendentes.
    _, corpo, _ = _get(servidor.porta, "/api/state", token=servidor.token)
    dados = json.loads(corpo)
    assert dados["pending_decisions"] == []


def test_escolha_vazia_e_recusada(servidor):
    acao = _AcaoFalsa("Qual?", ["A", "B"])
    id_card = servidor.publish_decision(acao)
    status, _ = _post(
        servidor.porta, f"/api/decision/{id_card}", servidor.token,
        {"escolha": "   "})
    assert status == 400
