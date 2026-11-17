"""Web Push: notificação no celular (Android e iPhone/PWA).

Arquitetura:

- Chave VAPID (par ECDSA P-256) gerada na primeira execução, guardada em
  `vapid_private.pem` na pasta de estado do app (`src/caminhos.py`; 0600,
  fora do controle de versão).
- Inscrições dos celulares (endpoint + chaves do cliente) em
  `.deepseek_ui/push_subs.json`.
- A entrega é feita pelo `pywebpush`, que cuida do JWT VAPID (ES256) e da
  cifragem do payload (aes128gcm).

Por que `pywebpush` e não `cryptography` na mão: assinar VAPID ES256 e cifrar o
payload do jeito que Mozilla/Google/Apple esperam tem detalhes sutis (padding,
HKDF, cabeçalho do Content-Encoding). A lib é fina e estável; escrever isso à
mão criaria mais um lugar para bug silencioso.

Sem `pywebpush` instalado, o módulo continua importável (`webpush = None`) e
`notificar()` devolve 0 — assim o app não quebra se a dependência faltar, só
não notifica.
"""

from __future__ import annotations

import base64
import json
import os
import threading
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

from src.caminhos import pasta_estado_app

try:
    from pywebpush import WebPushException, webpush
except ImportError:  # pragma: no cover — coberto pelo teste de 'webpush=None'
    webpush = None

    class WebPushException(Exception):
        """Placeholder quando a lib não está instalada.

        Mantém o nome da classe usada nos `except` para que o módulo seja
        importável mesmo sem a dependência.
        """


# Contato que vai no JWT VAPID. Serviços de push recusam um token sem `sub`.
# `mailto:` local é aceito por Mozilla/Google; Apple é mais rigorosa e um
# endereço real seria melhor — mas isso é decisão de configuração e pode
# ficar num arquivo `.deepseek_ui/push_config.json` quando virar necessidade.
VAPID_SUB = "mailto:noreply@localhost"


def _b64url(dados: bytes) -> str:
    """Base64 URL-safe sem padding — é o que o navegador aceita em applicationServerKey."""
    return base64.urlsafe_b64encode(dados).rstrip(b"=").decode("ascii")


def _chave_publica_b64(pem: str) -> str:
    """Extrai o ponto EC uncompressed (65 bytes) da chave privada, em b64url."""
    chave = serialization.load_pem_private_key(
        pem.encode("ascii"), password=None)
    pub = chave.public_key().public_bytes(
        encoding=serialization.Encoding.X962,
        format=serialization.PublicFormat.UncompressedPoint,
    )
    return _b64url(pub)


class PushManager:
    """Chave VAPID, inscrições dos celulares e entrega de notificação.

    Toda escrita em disco é protegida por um lock: `notificar()` pode ser
    chamado de uma thread de fundo (a notificação de uma decisão sai numa
    thread para não travar a GUI) e ao mesmo tempo o handler HTTP pode estar
    gravando uma inscrição nova.
    """

    def __init__(self, pasta_estado: str | Path | None = None):
        self.pasta = Path(pasta_estado) if pasta_estado else pasta_estado_app()
        self.pasta.mkdir(parents=True, exist_ok=True)
        self._priv_path = self.pasta / "vapid_private.pem"
        self._subs_path = self.pasta / "push_subs.json"
        self._lock = threading.Lock()
        self._priv_pem = self._carregar_ou_gerar_chave()
        self._pub_b64 = _chave_publica_b64(self._priv_pem)
        self._subs = self._carregar_subs()

    # ---------------- chaves ----------------

    def _carregar_ou_gerar_chave(self) -> str:
        """PEM PKCS8 sem cifra. Primeira execução gera; as seguintes releem."""
        if self._priv_path.is_file():
            try:
                texto = self._priv_path.read_text(encoding="utf-8")
                if texto.strip():
                    return texto
            except OSError:
                pass
        chave = ec.generate_private_key(ec.SECP256R1())
        pem = chave.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        ).decode("ascii")
        self._priv_path.write_text(pem, encoding="utf-8")
        try:
            os.chmod(self._priv_path, 0o600)
        except OSError:
            pass
        return pem

    def public_key(self) -> str:
        """Chave pública VAPID em base64url, para o navegador assinar a inscrição."""
        return self._pub_b64

    # ---------------- inscrições ----------------

    def _carregar_subs(self) -> list[dict]:
        try:
            dados = json.loads(self._subs_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        if not isinstance(dados, list):
            return []
        return [d for d in dados if isinstance(d, dict) and d.get("endpoint")]

    def _salvar_subs(self):
        try:
            self._subs_path.write_text(
                json.dumps(self._subs, ensure_ascii=False, indent=2),
                encoding="utf-8")
        except OSError:
            pass

    def listar(self) -> list[dict]:
        with self._lock:
            return [dict(s) for s in self._subs]

    def tem_inscricoes(self) -> bool:
        with self._lock:
            return bool(self._subs)

    def subscribe(self, inscricao: dict) -> bool:
        """Guarda (ou atualiza) uma inscrição. Exige endpoint + p256dh + auth."""
        endpoint = (inscricao or {}).get("endpoint")
        chaves = (inscricao or {}).get("keys")
        if not (isinstance(endpoint, str) and endpoint
                and isinstance(chaves, dict)
                and chaves.get("p256dh") and chaves.get("auth")):
            return False
        with self._lock:
            self._subs = [s for s in self._subs if s.get("endpoint") != endpoint]
            self._subs.append({
                "endpoint": endpoint,
                "keys": {
                    "p256dh": chaves["p256dh"],
                    "auth": chaves["auth"],
                },
            })
            self._salvar_subs()
        return True

    def unsubscribe(self, endpoint: str) -> bool:
        if not endpoint:
            return False
        with self._lock:
            antes = len(self._subs)
            self._subs = [s for s in self._subs if s.get("endpoint") != endpoint]
            if len(self._subs) == antes:
                return False
            self._salvar_subs()
        return True

    # ---------------- entrega ----------------

    def notificar(self, titulo: str, corpo: str = "", url: str = "/") -> int:
        """Entrega para cada inscrição ativa. Devolve quantas entregas OK.

        Não levanta em erro por inscrição: um endpoint morto não pode derrubar
        a entrega das outras. Inscrição que responde 404/410 é descartada — é
        como o serviço de push sinaliza "esse navegador não existe mais".
        """
        if webpush is None:
            return 0
        with self._lock:
            inscricoes = list(self._subs)
        if not inscricoes:
            return 0
        payload = json.dumps(
            {"title": titulo, "body": corpo, "url": url},
            ensure_ascii=False,
        )
        entregues = 0
        expiradas: list[str] = []
        for inscricao in inscricoes:
            try:
                webpush(
                    subscription_info=inscricao,
                    data=payload,
                    vapid_private_key=str(self._priv_path),
                    vapid_claims={"sub": VAPID_SUB},
                )
                entregues += 1
            except WebPushException as e:
                resposta = getattr(e, "response", None)
                codigo = getattr(resposta, "status_code", None)
                if codigo in (404, 410):
                    expiradas.append(inscricao.get("endpoint", ""))
            except Exception:
                # Qualquer outra falha (rede, TLS, payload) não derruba as
                # entregas seguintes nem a UI. O log fica para depois.
                pass
        if expiradas:
            with self._lock:
                self._subs = [
                    s for s in self._subs if s.get("endpoint") not in expiradas
                ]
                self._salvar_subs()
        return entregues
