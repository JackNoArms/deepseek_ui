"""Painel remoto: estado, decisões, notificações e comandos pelo celular.

Escuta só em `127.0.0.1` — quem expõe para a tailnet é o `tailscale serve`
(ou `tailscale funnel`, se um dia fizer sentido). O app nunca abre uma porta
para a internet por conta própria.

Autenticação: token gerado no arranque e guardado em
`remote_token` na pasta de estado do app (`src/caminhos.py`).
Aceita três formas, todas equivalentes para as rotas `/api/*`:

- `Authorization: Bearer <token>`
- cookie `remote_token=<token>` (o painel grava no primeiro carregamento)
- `?token=<token>` na URL (para abrir no celular pela primeira vez)

Rotas estáticas (`/sw.js`, `/manifest.webmanifest`, `/icon-*.png`,
`/remote_panel.css`, `/remote_panel.js`) não exigem token: alguns navegadores
as buscam sem cookie e nada nelas depende de sigilo.

O Service Worker faz **network-first**: toda requisição tenta a rede primeiro;
se falhar (offline), cai no cache.

A ponte com a GUI tem três sinais:

- `decision_answered` destranca um `QEventLoop` de decisão.
- `execute` recebe um callable e o roda na thread da GUI.
- `remote_action` avisa o PC (sem esperar retorno) que o celular fez algo.

`executar_na_gui` espera no máximo 5s; se estourar (diálogo modal aberto no
PC, por exemplo), devolve `{'erro': 'app_ocupado', 'dica': ...}` em vez de
segurar a requisição HTTP por 120s. Polling não emite `remote_action` — a
lista de métodos silenciosos está em `_COMANDOS_SILENCIOSOS`.
"""

from __future__ import annotations

import json
import os
import secrets
import struct
import threading
import time
import zlib
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from PyQt6.QtCore import QObject, pyqtSignal

from src.caminhos import arquivo_token, recurso
from src.push import PushManager
from src.theme import css_temas_remotos

_RAIZ_APP = recurso("src")
_TOKEN_PADRAO = str(arquivo_token())
PORTA_PADRAO = 8765

LIMITE_CORPO = 32 * 1024 * 1024
TIMEOUT_GUI = 5.0

_COMANDOS_SILENCIOSOS = frozenset({
    "_remote_get_state",
    "_remote_get_vapid",
    "_remote_list_projects",
    "_remote_list_vaults",
    "_remote_get_chat",
    "_remote_list_attachments",
    "_remote_list_tree",
    "_remote_browse",
    "_remote_buscar",
    "_remote_get_permissions",
    "_remote_decision_attach",
})


def _agora() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime())


def _garantir_token(caminho: str) -> str:
    os.makedirs(os.path.dirname(caminho), exist_ok=True)
    if os.path.isfile(caminho):
        try:
            with open(caminho, "r", encoding="utf-8") as f:
                token = f.read().strip()
            if token:
                return token
        except OSError:
            pass
    token = secrets.token_urlsafe(24)
    with open(caminho, "w", encoding="utf-8") as f:
        f.write(token)
    try:
        os.chmod(caminho, 0o600)
    except OSError:
        pass
    return token


_COR_ACCENT = (0x5B, 0x7C, 0xFA)


def _png_solido(largura: int, altura: int, cor: tuple[int, int, int]) -> bytes:
    def chunk(tipo: bytes, dados: bytes) -> bytes:
        return (struct.pack(">I", len(dados)) + tipo + dados
                + struct.pack(">I", zlib.crc32(tipo + dados) & 0xFFFFFFFF))
    ihdr = struct.pack(">IIBBBBB", largura, altura, 8, 2, 0, 0, 0)
    r, g, b = cor
    linha = b"\x00" + bytes((r, g, b)) * largura
    idat = zlib.compress(linha * altura)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", idat) + chunk(b"IEND", b""))


_ICONE_180 = _png_solido(180, 180, _COR_ACCENT)
_ICONE_192 = _png_solido(192, 192, _COR_ACCENT)
_ICONE_512 = _png_solido(512, 512, _COR_ACCENT)


def _ler_arquivo(nome: str) -> bytes:
    caminho = _RAIZ_APP / nome
    try:
        return caminho.read_bytes()
    except OSError:
        return b""


def _descrever_acao(metodo: str, kwargs: dict) -> str:
    caminho = kwargs.get("caminho") or "?"
    if metodo == "_remote_open_project":
        return f"abriu projeto {Path(str(caminho)).name or '?'}"
    if metodo == "_remote_open_vault":
        return f"vinculou vault {Path(str(caminho)).name or '?'}"
    if metodo == "_remote_read_file":
        return f"leu {caminho}"
    if metodo == "_remote_write_file":
        acao = "criou" if kwargs.get("criar") else "gravou"
        return f"{acao} {caminho}"
    if metodo == "_remote_delete_file":
        return f"apagou {caminho}"
    if metodo == "_remote_new_folder":
        return f"criou pasta {caminho}"
    if metodo == "_remote_send_message":
        return "enviou mensagem"
    if metodo == "_remote_attach":
        try:
            n = len(kwargs.get("anexos_json") or [])
        except TypeError:
            n = 0
        return f"anexou {n} arquivo(s)"
    if metodo == "_remote_new_chat":
        return "iniciou nova conversa"
    if metodo == "_remote_set_permissions":
        return "alterou permissões"
    if metodo == "_remote_cancel_queue":
        return "cancelou uma mensagem da fila"
    if metodo == "_remote_clear_queue":
        return "limpou a fila"
    if metodo == "_remote_edit_queue":
        return "editou uma mensagem da fila"
    return metodo.replace("_remote_", "") or "ação remota"


SERVICE_WORKER = r"""
const VERSAO = 'deepseek-ui-v2';
self.addEventListener('install', (event) => {
  event.waitUntil((async () => {
    const nomes = await caches.keys();
    await Promise.all(nomes.filter(n => n !== VERSAO).map(n => caches.delete(n)));
    await self.skipWaiting();
  })());
});
self.addEventListener('activate', (event) => {
  event.waitUntil((async () => { await self.clients.claim(); })());
});
self.addEventListener('fetch', (event) => {
  const req = event.request;
  if (req.method !== 'GET') return;
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;
  event.respondWith((async () => {
    try {
      const resp = await fetch(req);
      if (resp && resp.ok) {
        const cache = await caches.open(VERSAO);
        try { await cache.put(req, resp.clone()); } catch (e) {}
      }
      return resp;
    } catch (e) {
      const cached = await caches.match(req);
      if (cached) return cached;
      throw e;
    }
  })());
});
self.addEventListener('push', (event) => {
  let data = {};
  try { data = event.data ? event.data.json() : {}; } catch (e) {}
  const titulo = data.title || 'DeepSeek UI';
  const corpo = data.body || '';
  const url = data.url || '/';
  event.waitUntil(self.registration.showNotification(titulo, {
    body: corpo, icon: '/icon-192.png', badge: '/icon-192.png',
    tag: 'deepseek-decisao', renotify: true, data: { url: url }
  }));
});
self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  const url = (event.notification.data && event.notification.data.url) || '/';
  event.waitUntil((async () => {
    const lista = await self.clients.matchAll({type: 'window', includeUncontrolled: true});
    for (const c of lista) {
      if (c.url.startsWith(self.location.origin)) {
        try { await c.navigate(url); } catch (e) {}
        return c.focus();
      }
    }
    if (self.clients.openWindow) return self.clients.openWindow(url);
  })());
});
"""


MANIFEST = json.dumps({
    "name": "DeepSeek UI Remoto", "short_name": "DeepSeek",
    "start_url": "/", "scope": "/", "display": "standalone",
    "background_color": "#0F1115", "theme_color": "#15181E",
    "icons": [
        {"src": "/icon-180.png", "sizes": "180x180", "type": "image/png",
         "purpose": "any"},
        {"src": "/icon-192.png", "sizes": "192x192", "type": "image/png"},
        {"src": "/icon-512.png", "sizes": "512x512", "type": "image/png"},
    ],
}, ensure_ascii=False, indent=2).encode("utf-8")


class RemoteBridge(QObject):
    """Ponte entre o servidor HTTP e a thread da GUI.

    - `decision_answered` destranca o `QEventLoop` de uma decisão.
    - `execute` recebe um callable e o roda na thread da GUI.
    - `remote_action` é one-way: aviso de que uma ação remota aconteceu.
    """

    decision_answered = pyqtSignal(str, str)
    execute = pyqtSignal(object)
    remote_action = pyqtSignal(str, str)  # (metodo, descrição amigável)


class RemoteServer:
    """Estado publicado, decisões, comandos e notificações push."""

    def __init__(self, porta: int = PORTA_PADRAO, token_path: str | None = None,
                 bridge: RemoteBridge | None = None,
                 push: PushManager | None = None):
        self.porta = int(porta)
        self.token = _garantir_token(token_path or _TOKEN_PADRAO)
        self.bridge = bridge or RemoteBridge()
        self.handlers = None
        self._lock = threading.Lock()
        self._state = {
            "project": None, "status": "desconectado", "status_tone": "muted",
            "connected": False, "agent_active": False, "queue": 0,
            "updated_at": _agora(),
        }
        self._decisions: dict[str, dict] = {}
        self._httpd: _HTTPD | None = None
        self._thread: threading.Thread | None = None
        try:
            self.push = push or PushManager()
        except Exception as e:
            print(f"Push indisponível: {type(e).__name__} - {e}")
            self.push = None

    def set_handlers(self, handlers):
        self.handlers = handlers

    def start(self):
        if self._httpd is not None:
            return
        self._httpd = _HTTPD(("127.0.0.1", self.porta), _Handler, self)
        self.porta = self._httpd.server_address[1]
        self._thread = threading.Thread(
            target=self._httpd.serve_forever, daemon=True)
        self._thread.start()

    def stop(self):
        httpd, self._httpd = self._httpd, None
        thread, self._thread = self._thread, None
        if httpd is not None:
            try:
                httpd.shutdown()
            except Exception:
                pass
            try:
                httpd.server_close()
            except Exception:
                pass
        if thread is not None:
            thread.join(timeout=2)

    def update(self, **campos):
        with self._lock:
            self._state.update(campos)
            self._state["updated_at"] = _agora()

    def snapshot(self) -> dict:
        with self._lock:
            dados = dict(self._state)
            dados["pending_decisions"] = [
                {k: d[k] for k in
                 ("id", "pergunta", "opcoes", "recomendada", "motivo", "criado")}
                for d in self._decisions.values() if not d["resolved"]
            ]
        return dados

    def executar_na_gui(self, metodo: str, timeout: float = TIMEOUT_GUI,
                        **kwargs):
        """Roda `handlers.<metodo>(**kwargs)` na thread da GUI.

        Espera no máximo `timeout` (5s por padrão). Se estourar — cenário
        típico é diálogo modal aberto no PC — devolve `app_ocupado` com dica.
        Não bloqueia o handler HTTP por minutos. Ao final de um comando de
        ação bem-sucedido (fora da lista silenciosa), emite `remote_action`.
        """
        if self.handlers is None:
            return {"erro": "servidor sem janela registrada"}
        alvo = getattr(self.handlers, metodo, None)
        if alvo is None or not callable(alvo):
            return {"erro": f"comando desconhecido: {metodo}"}

        holder: dict = {"resultado": None, "evento": threading.Event()}

        def tarefa():
            try:
                holder["resultado"] = alvo(**kwargs)
            except Exception as e:
                holder["resultado"] = {"erro": f"{type(e).__name__}: {e}"}
            finally:
                holder["evento"].set()

        self.bridge.execute.emit(tarefa)
        if not holder["evento"].wait(timeout):
            return {
                "erro": "app_ocupado",
                "dica": "Tem um diálogo aberto no PC (revisão, acesso, etc.) "
                        "ou a interface está ocupada. Feche no PC e tente de novo.",
            }
        resultado = holder["resultado"] or {"erro": "resposta vazia"}
        if (metodo not in _COMANDOS_SILENCIOSOS
                and not (isinstance(resultado, dict) and resultado.get("erro"))):
            try:
                self.bridge.remote_action.emit(
                    metodo, _descrever_acao(metodo, kwargs))
            except Exception:
                pass
        return resultado

    def publish_decision(self, acao) -> str:
        extras = dict(getattr(acao, "extras", {}) or {})
        id_card = secrets.token_urlsafe(6)
        with self._lock:
            self._decisions[id_card] = {
                "id": id_card,
                "pergunta": str(extras.get("pergunta") or ""),
                "opcoes": [str(o) for o in (extras.get("opcoes") or [])],
                "recomendada": extras.get("recomendada"),
                "motivo": extras.get("motivo"),
                "resolved": False, "escolha": None, "criado": _agora(),
            }
        self._notificar_decisao(id_card, extras)
        return id_card

    def _notificar_decisao(self, id_card: str, extras: dict):
        if self.push is None or not self.push.tem_inscricoes():
            return
        pergunta = str(extras.get("pergunta") or "")
        titulo = "Decisão necessária"
        corpo = pergunta if len(pergunta) <= 180 else pergunta[:177] + "…"

        def tarefa():
            try:
                self.push.notificar(titulo, corpo, "/")
            except Exception as e:
                print(f"Falha ao notificar: {type(e).__name__} - {e}")

        threading.Thread(target=tarefa, daemon=True).start()

    def pendente(self, id_card: str) -> bool:
        with self._lock:
            d = self._decisions.get(id_card)
            return d is not None and not d["resolved"]

    def answer(self, id_card: str, escolha: str) -> bool:
        with self._lock:
            d = self._decisions.get(id_card)
            if d is None or d["resolved"]:
                return False
            d["resolved"] = True
            d["escolha"] = escolha
        self.bridge.decision_answered.emit(id_card, escolha)
        return True

    def mark_resolved(self, id_card: str, escolha: str):
        with self._lock:
            d = self._decisions.get(id_card)
            if d is not None and not d["resolved"]:
                d["resolved"] = True
                d["escolha"] = escolha


class _HTTPD(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, endereco, handler, remoto: RemoteServer):
        super().__init__(endereco, handler)
        self.remoto = remoto


COMANDOS_GET = {
    "/api/state": ("get_state", ()),
    "/api/vapid-public-key": ("get_vapid", ()),
    "/api/projects": ("list_projects", ()),
    "/api/vaults": ("list_vaults", ()),
    "/api/chat": ("get_chat", ()),
    "/api/attachments": ("list_attachments", ()),
    "/api/permissions": ("get_permissions", ()),
}

COMANDOS_POST = {
    "/api/open-project": ("open_project", ("caminho",)),
    "/api/open-vault": ("open_vault", ("caminho",)),
    "/api/tree": ("list_tree", ("tipo",)),
    "/api/read-file": ("read_file", ("tipo", "caminho")),
    "/api/write-file": ("write_file", ("tipo", "caminho", "conteudo", "criar")),
    "/api/delete-file": ("delete_file", ("tipo", "caminho")),
    "/api/new-folder": ("new_folder", ("tipo", "caminho")),
    "/api/browse": ("browse", ("caminho",)),
    "/api/send": ("send_message", ("texto", "agente")),
    "/api/search": ("buscar", ("termo", "em", "ext")),
    "/api/attach": ("attach", ("anexos_json",)),
    "/api/new-chat": ("new_chat", ()),
    "/api/queue/cancel": ("cancel_queue", ("id",)),
    "/api/queue/clear": ("clear_queue", ()),
    "/api/queue/edit": ("edit_queue", ("id", "texto")),
    "/api/permissions": ("set_permissions", ("mode", "grants", "confirm_reads")),
}


class _Handler(BaseHTTPRequestHandler):
    server_version = "DeepSeekUIRemote/0.5"

    def log_message(self, fmt, *args):
        return

    def _remoto(self) -> RemoteServer:
        return self.server.remoto  # type: ignore[attr-defined]

    def _autorizado(self, query) -> bool:
        token = self._remoto().token
        auth = self.headers.get("Authorization", "") or ""
        if auth.lower().startswith("bearer "):
            if secrets.compare_digest(auth[7:].strip(), token):
                return True
        cookie = self.headers.get("Cookie", "") or ""
        for parte in cookie.split(";"):
            chave, _, valor = parte.strip().partition("=")
            if chave == "remote_token" and secrets.compare_digest(valor, token):
                return True
        valores = query.get("token") or []
        if valores and secrets.compare_digest(valores[0], token):
            return True
        return False

    def _responder(self, status, corpo: bytes, tipo: str, extra=None):
        self.send_response(status)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(corpo)))
        self.send_header("Cache-Control",
                         "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        if extra:
            for chave, valor in extra:
                self.send_header(chave, valor)
        self.end_headers()
        if corpo:
            self.wfile.write(corpo)

    def _json(self, status, payload, extra=None):
        corpo = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self._responder(status, corpo, "application/json; charset=utf-8", extra)

    def _ler_json(self):
        try:
            tamanho = int(self.headers.get("Content-Length") or "0")
        except ValueError:
            tamanho = 0
        if tamanho < 0 or tamanho > LIMITE_CORPO:
            return None
        corpo = self.rfile.read(tamanho) if tamanho > 0 else b""
        try:
            return json.loads(corpo.decode("utf-8") or "{}")
        except (json.JSONDecodeError, UnicodeDecodeError):
            return None

    def _estatico(self, caminho: str) -> bool:
        if caminho == "/sw.js":
            self._responder(HTTPStatus.OK, SERVICE_WORKER.encode("utf-8"),
                            "application/javascript; charset=utf-8")
            return True
        if caminho == "/manifest.webmanifest":
            self._responder(HTTPStatus.OK, MANIFEST,
                            "application/manifest+json; charset=utf-8")
            return True
        if caminho == "/icon-180.png":
            self._responder(HTTPStatus.OK, _ICONE_180, "image/png")
            return True
        if caminho == "/icon-192.png":
            self._responder(HTTPStatus.OK, _ICONE_192, "image/png")
            return True
        if caminho == "/icon-512.png":
            self._responder(HTTPStatus.OK, _ICONE_512, "image/png")
            return True
        if caminho == "/remote_theme.css":
            self._responder(HTTPStatus.OK,
                            css_temas_remotos().encode("utf-8"),
                            "text/css; charset=utf-8")
            return True
        if caminho == "/remote_panel.css":
            self._responder(HTTPStatus.OK, _ler_arquivo("remote_panel.css"),
                            "text/css; charset=utf-8")
            return True
        if caminho == "/remote_panel.js":
            self._responder(HTTPStatus.OK, _ler_arquivo("remote_panel.js"),
                            "application/javascript; charset=utf-8")
            return True
        return False

    def do_GET(self):
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        if self._estatico(parsed.path):
            return
        if not self._autorizado(query):
            return self._json(HTTPStatus.UNAUTHORIZED, {"erro": "token inválido"})
        if parsed.path == "/":
            html = _ler_arquivo("remote_panel.html")
            if not html:
                html = b"<h1>painel remoto sem HTML</h1>"
            return self._responder(
                HTTPStatus.OK, html, "text/html; charset=utf-8",
                [("Set-Cookie",
                  f"remote_token={self._remoto().token}; HttpOnly; "
                  "Path=/; SameSite=Strict")])
        rota = COMANDOS_GET.get(parsed.path)
        if rota is None:
            return self._json(HTTPStatus.NOT_FOUND, {"erro": "rota desconhecida"})
        nome, _ = rota
        if nome == "get_state":
            return self._json(HTTPStatus.OK, self._remoto().snapshot())
        if nome == "get_vapid":
            push = self._remoto().push
            if push is None:
                return self._json(HTTPStatus.SERVICE_UNAVAILABLE,
                                  {"erro": "push indisponível"})
            return self._json(HTTPStatus.OK, {"key": push.public_key()})
        return self._json(
            HTTPStatus.OK,
            self._remoto().executar_na_gui(f"_remote_{nome}"))

    def do_POST(self):
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        if not self._autorizado(query):
            return self._json(HTTPStatus.UNAUTHORIZED, {"erro": "token inválido"})
        if parsed.path == "/api/subscribe":
            dados = self._ler_json()
            if dados is None:
                return self._json(HTTPStatus.BAD_REQUEST, {"erro": "corpo inválido"})
            push = self._remoto().push
            if push is None:
                return self._json(HTTPStatus.SERVICE_UNAVAILABLE,
                                  {"erro": "push indisponível"})
            if not push.subscribe(dados):
                return self._json(HTTPStatus.BAD_REQUEST,
                                  {"erro": "inscrição malformada"})
            return self._json(HTTPStatus.OK, {"ok": True})
        if parsed.path == "/api/unsubscribe":
            dados = self._ler_json()
            if not isinstance(dados, dict) or not isinstance(dados.get("endpoint"), str):
                return self._json(HTTPStatus.BAD_REQUEST,
                                  {"erro": "endpoint ausente"})
            push = self._remoto().push
            removido = bool(push and push.unsubscribe(dados["endpoint"]))
            return self._json(HTTPStatus.OK, {"ok": removido})
        prefixo = "/api/decision/"
        if parsed.path.startswith(prefixo):
            id_card = parsed.path[len(prefixo):]
            dados = self._ler_json()
            if not isinstance(dados, dict):
                return self._json(HTTPStatus.BAD_REQUEST, {"erro": "corpo inválido"})
            escolha = dados.get("escolha")
            if not isinstance(escolha, str) or not escolha.strip():
                return self._json(HTTPStatus.BAD_REQUEST, {"erro": "escolha vazia"})
            if not self._remoto().pendente(id_card):
                return self._json(HTTPStatus.CONFLICT,
                                  {"erro": "decisão já resolvida ou desconhecida"})
            anexos_json = dados.get("anexos_json")
            if anexos_json:
                anexado = self._remoto().executar_na_gui(
                    "_remote_decision_attach", id_card=id_card,
                    anexos_json=anexos_json)
                if isinstance(anexado, dict) and anexado.get("erro"):
                    return self._json(HTTPStatus.BAD_REQUEST, anexado)
            if not self._remoto().answer(id_card, escolha.strip()):
                return self._json(HTTPStatus.CONFLICT,
                                  {"erro": "decisão já resolvida ou desconhecida"})
            return self._json(HTTPStatus.OK, {"ok": True})
        rota = COMANDOS_POST.get(parsed.path)
        if rota is None:
            return self._json(HTTPStatus.NOT_FOUND, {"erro": "rota desconhecida"})
        nome, campos = rota
        dados = self._ler_json()
        if dados is None:
            return self._json(HTTPStatus.BAD_REQUEST, {"erro": "corpo inválido"})
        if not isinstance(dados, dict):
            return self._json(HTTPStatus.BAD_REQUEST, {"erro": "corpo precisa ser objeto"})
        kwargs = {}
        for campo in campos:
            if campo in dados:
                kwargs[campo] = dados[campo]
        return self._json(
            HTTPStatus.OK,
            self._remoto().executar_na_gui(f"_remote_{nome}", **kwargs))
