"""Camada entre a GUI e o Selenium.

A GUI nunca lê o estado dos toggles por conta própria: um poller espelha o que a
página realmente mostra, então DeepThink/Search ficam corretos mesmo quando o
usuário os altera direto no navegador.
"""

import os
import threading
import time

from src.wrapper import DeepSeekWrapper, ErroTamanho, _n


class Controller:
    POLL_INTERVAL = 2.0

    def __init__(self):
        self.wrapper = DeepSeekWrapper()
        self.is_connected = False
        self.deepthink_on = False
        self.search_on = False
        # Começa disponível: o poller corrige assim que lê a página. Se começasse
        # False e a leitura falhasse, o chip ficaria morto para sempre.
        self.search_available = True
        self.gui = None
        self._poll_thread = None
        self._stop_poll = threading.Event()

    def set_gui(self, gui):
        self.gui = gui

    # ---------------- conexão ----------------

    def connect(self, headless=False):
        if self.is_connected:
            return True

        success = self.wrapper.open(headless)
        self.is_connected = success

        if self.gui:
            if success:
                self._sync_states()
                self.gui.update_status("Conectado", "success")
                self.gui.enable_controls(True)
                self._start_poll()
            elif self.wrapper.needs_login:
                # O Chrome continua aberto na tela de login: o usuário entra na
                # conta e clica em Conectar de novo.
                self.gui.update_status(
                    "Faça login no Chrome que abriu e clique em Conectar de novo", "danger")
                self.gui.enable_controls(False)
            else:
                self.gui.update_status("Falha na conexão", "danger")
                self.gui.enable_controls(False)
        return success

    def disconnect(self):
        self._stop_poll.set()
        # Fecha sempre, não só quando conectado: se o login ficou pendente o
        # driver existe sem `is_connected`, e o Chrome sobraria aberto.
        self.wrapper.close()
        self.is_connected = False
        if self.gui:
            self.gui.update_status("Desconectado", "muted")
            self.gui.enable_controls(False)

    # ---------------- espelhamento de estado ----------------

    def _start_poll(self):
        self._stop_poll.clear()
        self._poll_thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._poll_thread.start()

    def _poll_loop(self):
        while not self._stop_poll.is_set() and self.is_connected:
            time.sleep(self.POLL_INTERVAL)
            if self._stop_poll.is_set() or not self.is_connected:
                break
            try:
                self._sync_states()
            except Exception:
                pass

    def _sync_states(self):
        """Lê o estado real da página e reflete na GUI."""
        if not self.is_connected:
            return None

        state = self.wrapper.read_state()

        deepthink = bool(state.get("deepthink"))
        if deepthink != self.deepthink_on:
            self.deepthink_on = deepthink
            if self.gui:
                self.gui.update_deepthink(deepthink)

        search = bool(state.get("search"))
        if search != self.search_on:
            self.search_on = search
            if self.gui:
                self.gui.update_search(search)

        available = bool(state.get("search_available", True))
        if available != self.search_available:
            self.search_available = available
            if self.gui:
                self.gui.update_search_available(available)

        return state

    # ---------------- ações ----------------

    def toggle_deepthink(self):
        if not self.is_connected:
            return False
        result = self.wrapper.toggle_deepthink()
        self._sync_states()
        return result

    def toggle_search(self):
        if not self.is_connected:
            return False
        result = self.wrapper.toggle_search()
        self._sync_states()
        return result

    def new_chat(self):
        return self.wrapper.new_chat() if self.is_connected else False

    def list_conversations(self):
        return self.wrapper.list_conversations() if self.is_connected else []

    def open_conversation(self, url):
        return self.wrapper.open_conversation(url) if self.is_connected else False

    def extract_history(self):
        return self.wrapper.extract_history() if self.is_connected else []

    def extract_last_response(self):
        return self.wrapper.extract_last_response() if self.is_connected else None

    @property
    def ultima_captura(self) -> dict:
        """Como a última resposta foi obtida (fonte, status, tokens, tamanhos)."""
        return dict(getattr(self.wrapper, "ultima_captura", {}) or {})

    def current_url(self):
        return self.wrapper.current_url()

    def send_message(self, text, on_update=None, arquivos=None, on_sent=None):
        """`arquivos` sobem para o DeepSeek ANTES do texto (imagem colada, etc.)."""
        if not self.is_connected:
            raise RuntimeError("Navegador não conectado.")
        arquivos = list(arquivos or [])
        if not text.strip() and not arquivos:
            raise ValueError("Digite uma mensagem ou anexe um arquivo.")

        if self.gui:
            self.gui.update_status("Preparando envio ao DeepSeek…", "accent")
        try:
            for i, caminho in enumerate(arquivos, 1):
                if self.gui:
                    self.gui.update_status(
                        f"Enviando anexo {i}/{len(arquivos)}…", "accent")
                if not self.wrapper.anexar(caminho):
                    raise RuntimeError(
                        f"Falhou ao anexar {os.path.basename(caminho)}; "
                        "a mensagem não foi enviada.")

            if self.gui:
                self.gui.update_status("Enviando mensagem ao DeepSeek…", "accent")

            def enviado():
                if self.gui:
                    self.gui.update_status(
                        "Mensagem enviada; aguardando resposta…", "accent")
                if on_sent:
                    on_sent()

            response = self.wrapper.send_message(
                text, on_update=on_update, on_sent=enviado)
            if self.gui:
                tokens = self.ultima_captura.get("tokens")
                self.gui.update_status(
                    f"Pronto · conversa com {_n(tokens)} tokens" if tokens
                    else "Pronto", "success")
            return response or "Sem resposta."
        except ErroTamanho as e:
            # Mantém o tipo: o agente decide diferente para envio e resposta.
            if self.gui:
                self.gui.update_status(f"Erro de tamanho: {e}", "danger")
            raise
        except Exception as e:
            msg = f"Erro: {e}"
            if self.gui:
                self.gui.update_status(msg, "danger")
            raise RuntimeError(msg) from e
