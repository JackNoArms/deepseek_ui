"""Ponte entre o Controller (threads de fundo) e a UI Qt (thread única).

O Controller chama `gui.update_status(...)`, `gui.update_deepthink(...)` etc. a
partir do poller e da thread de envio. No Qt, widget só pode ser tocado pela
thread da GUI. Este objeto implementa a mesma interface, mas cada método apenas
EMITE um sinal Qt — a conexão enfileirada entrega na thread certa.
"""

from PyQt6.QtCore import QObject, pyqtSignal


class GuiBridge(QObject):
    status = pyqtSignal(str, str)  # (mensagem, tom)
    controls_enabled = pyqtSignal(bool)
    deepthink = pyqtSignal(bool)
    search = pyqtSignal(bool)
    search_available = pyqtSignal(bool)

    # --- interface esperada pelo Controller ---
    def update_status(self, msg, tone="muted"):
        self.status.emit(msg, tone)

    def enable_controls(self, enabled):
        self.controls_enabled.emit(bool(enabled))

    def update_deepthink(self, state):
        self.deepthink.emit(bool(state))

    def update_search(self, state):
        self.search.emit(bool(state))

    def update_search_available(self, available):
        self.search_available.emit(bool(available))
