"""Widgets e workers do updater. Separado de `window.py` para caber.

`src/updater.py` é backend puro (sem Qt). Aqui ficam as classes que
precisam de Qt:

- `UpdaterWorker(QThread)` — busca o manifesto em thread própria.
- `DownloadWorker(QThread)` — baixa o `.exe` + confere hash.
- `BannerAtualizacao(QFrame)` — barra compacta no topo, sem roubar foco.

Contrato com `window.py`:

- `UpdaterWorker(manual)`:
    `atualizacao(Manifesto|None)` quando termina bem (None = sem
    novidade, URL placeholder, ou versão ignorada).
    `erro(str)` para `ManifestoErro` ou exceção.
    `manual=True` faz a UI mostrar até os erros; `manual=False` engole.

- `DownloadWorker(manifesto)`:
    `progresso(baixado, total)` a cada ~1 MB; `total=0` quando
    `Content-Length` falta.
    `ok(caminho)` só depois que o `sha256` bateu.
    `erro(motivo)` para rede, hash errado, disco cheio.

- `BannerAtualizacao(manifesto)`:
    Sinais `atualizar` / `adiar` / `ver_notas`.
    `set_progresso(baixado, total)` desabilita os botões e mostra %.
    `set_erro(motivo)` reabilita e mostra o motivo.
    `set_bloqueado(b)` desabilita **só o Atualizar** com tooltip.
"""

from __future__ import annotations

import tempfile
import time
from pathlib import Path

from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
)

from src import updater


class UpdaterWorker(QThread):
    """Verifica o manifesto remoto em background, sem bloquear a UI."""

    atualizacao = pyqtSignal(object)  # Manifesto | None
    erro = pyqtSignal(str)

    def __init__(self, manual: bool = False):
        super().__init__()
        self.manual = manual

    def run(self):
        try:
            cfg = updater.carregar_config()
            url = updater.url_efetiva(cfg)
            if updater.eh_placeholder(url):
                self.atualizacao.emit(None)
                return
            manifesto = updater.buscar_manifesto(url)
            resultado = updater.verificar(manifesto)
            if resultado != "atualizar":
                self.atualizacao.emit(None)
                return
            # Respeita o "Depois por 24 h" do usuário para essa versão.
            if (cfg.versao_ignorada == manifesto.versao
                    and cfg.ignorada_ate
                    and time.strftime("%Y-%m-%dT%H:%M:%S") < cfg.ignorada_ate):
                self.atualizacao.emit(None)
                return
            self.atualizacao.emit(manifesto)
        except updater.ManifestoErro as e:
            self.erro.emit(e.motivo)
        except Exception as e:
            self.erro.emit(f"{type(e).__name__}: {e}")


class DownloadWorker(QThread):
    """Baixa o `.exe` do manifesto e confere o `sha256` antes de emitir ok."""

    progresso = pyqtSignal(int, int)
    ok = pyqtSignal(str)
    erro = pyqtSignal(str)

    def __init__(self, manifesto):
        super().__init__()
        self.manifesto = manifesto

    def run(self):
        try:
            destino = updater.baixar_e_verificar(
                self.manifesto, Path(tempfile.gettempdir()),
                ao_progredir=lambda b, t: self.progresso.emit(b, t))
            self.ok.emit(str(destino))
        except updater.ManifestoErro as e:
            self.erro.emit(e.motivo)
        except Exception as e:
            self.erro.emit(f"{type(e).__name__}: {e}")


class BannerAtualizacao(QFrame):
    """Barra compacta no topo do chat, sem roubar foco.

    Fica até o usuário escolher: `Atualizar`, `Depois` (silencia 24 h) ou
    `Ver notas` (QMessageBox simples). Durante o download, os botões somem
    e o texto vira progresso; em erro, o motivo substitui a linha e os
    botões voltam. `set_bloqueado(True)` desliga só o `Atualizar` quando
    há agente/envio/fila em andamento — o resto continua.
    """

    atualizar = pyqtSignal()
    adiar = pyqtSignal()
    ver_notas = pyqtSignal()

    def __init__(self, manifesto, parent=None):
        super().__init__(parent)
        self.setObjectName("updateBanner")
        self.manifesto = manifesto

        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 8, 12, 8)
        lay.setSpacing(10)

        self.lbl = QLabel(f"Atualização disponível: v{manifesto.versao}")
        self.lbl.setObjectName("updateText")
        self.lbl.setWordWrap(True)
        lay.addWidget(self.lbl, 1)

        self.btn_notas = QPushButton("Ver notas")
        self.btn_notas.setObjectName("openFolder")
        self.btn_notas.clicked.connect(self.ver_notas.emit)
        lay.addWidget(self.btn_notas)

        self.btn_depois = QPushButton("Depois")
        self.btn_depois.setObjectName("openFolder")
        self.btn_depois.clicked.connect(self.adiar.emit)
        lay.addWidget(self.btn_depois)

        self.btn_atualizar = QPushButton(f"Atualizar para v{manifesto.versao}")
        self.btn_atualizar.setObjectName("send")
        self.btn_atualizar.clicked.connect(self.atualizar.emit)
        lay.addWidget(self.btn_atualizar)

    def set_progresso(self, baixado: int, total: int):
        if total > 0:
            pct = int(baixado * 100 / total)
            self.lbl.setText(
                f"Baixando v{self.manifesto.versao}… {pct}% "
                f"({baixado // 1024} / {total // 1024} KB)")
        else:
            self.lbl.setText(
                f"Baixando v{self.manifesto.versao}… {baixado // 1024} KB")
        for b in (self.btn_atualizar, self.btn_depois, self.btn_notas):
            b.setEnabled(False)

    def set_erro(self, motivo: str):
        self.lbl.setText(f"Falha ao atualizar: {motivo}")
        for b in (self.btn_atualizar, self.btn_depois, self.btn_notas):
            b.setEnabled(True)

    def set_bloqueado(self, bloqueado: bool):
        self.btn_atualizar.setEnabled(not bloqueado)
        self.btn_atualizar.setToolTip(
            "Termine a tarefa atual antes de atualizar" if bloqueado else "")
