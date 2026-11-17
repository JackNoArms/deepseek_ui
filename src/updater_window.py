"""Wiring do updater na `MainWindow` — via mixin para caber o diff.

Separa três responsabilidades de propósito:

- `src/updater.py` — backend puro (rede, hash, versões).
- `src/updater_ui.py` — widgets e workers (QThread, QFrame).
- **este arquivo** — onde as coisas se juntam com a `MainWindow`.

Por que um mixin em vez de código dentro de `window.py`: `window.py` já tem
~2000 linhas e cada `modify` reenvia o arquivo inteiro. Aqui concentramos
~150 linhas de fiação com hooks mínimos:

    class MainWindow(UpdaterMixin, RemoteHandlersMixin, QMainWindow):
        ...

O `__init__` do mixin chama `super().__init__(*a, **kw)` primeiro — o que
cai no `MainWindow.__init__` real — e depois agenda:

1. Timer de 6 h + checagem em 30 s (via `QTimer.singleShot`).
2. Instalação das ações no menu Tema (`Verificar atualizações`,
   `Configurar URL de atualização`), num `singleShot` de 500 ms para
   garantir que `btn_tema` já exista.

Não é bonito; é o mínimo de acoplamento para caber no orçamento de saída do
modelo sem quebrar o padrão da `MainWindow`.
"""

from __future__ import annotations

import time
from pathlib import Path

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication, QInputDialog, QMessageBox

from src import updater
from src.__version__ import __version__ as APP_VERSION
from src.updater_ui import BannerAtualizacao, DownloadWorker, UpdaterWorker


class UpdaterMixin:
    """Mixin com toda a fiação do updater. Requer `centralWidget()` e
    `_on_status(msg, tom)` do host; o resto é opcional (`_ocupado`).

    `AppError` e `_updater_worker` etc. são criados por preguiça: até o
    primeiro tick, o estado fica em `None`. Se o host não tem `_ocupado`,
    o banner nunca é bloqueado.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Estado — todos `None` até o primeiro uso.
        self._timer_updater = None
        self._updater_worker = None
        self._download_worker = None
        self.banner_update = None
        self._manifesto_pendente = None
        # Agenda os dois setups num singleShot, para garantir que o
        # `__init__` do host terminou (centralWidget, btn_tema, etc.).
        QTimer.singleShot(0, self._instalar_updater)

    # ---------------- instalação ----------------

    def _instalar_updater(self):
        self._timer_updater = QTimer(self)
        self._timer_updater.timeout.connect(
            lambda: self._checar_atualizacao(manual=False))
        self._timer_updater.start(6 * 3600 * 1000)
        QTimer.singleShot(
            30_000, lambda: self._checar_atualizacao(manual=False))
        # Instala as ações no menu Tema. 500 ms é folga para o
        # `_build_header` do host já ter criado `btn_tema`.
        QTimer.singleShot(500, self._instalar_acoes_menu_tema)

    def _instalar_acoes_menu_tema(self):
        btn = getattr(self, "btn_tema", None)
        if btn is None:
            return
        menu = btn.menu()
        if menu is None:
            return
        # Evita duplicar caso o mixin seja reinstalado.
        if getattr(self, "_updater_menu_instalado", False):
            return
        menu.addSeparator()
        menu.addAction(
            "Verificar atualizações…",
            lambda: self._checar_atualizacao(manual=True))
        menu.addAction(
            "Configurar URL de atualização…",
            self._configurar_url_atualizacao)
        self._updater_menu_instalado = True

    def _parar_updater(self):
        """Para timer e workers. Chamado do `closeEvent` do host."""
        if self._timer_updater is not None:
            try:
                self._timer_updater.stop()
            except RuntimeError:
                pass
            self._timer_updater = None
        if self._updater_worker is not None:
            try:
                self._updater_worker.wait(2000)
            except RuntimeError:
                pass
            self._updater_worker = None
        if self._download_worker is not None:
            try:
                self._download_worker.wait(2000)
            except RuntimeError:
                pass
            self._download_worker = None

    # ---------------- checagem ----------------

    def _checar_atualizacao(self, manual: bool = False):
        if self._updater_worker is not None and self._updater_worker.isRunning():
            if manual:
                self._on_status("Já estou verificando…", "muted")
            return
        if manual:
            self._on_status("Verificando atualizações…", "muted")
        worker = UpdaterWorker(manual=manual)
        worker.atualizacao.connect(
            lambda m: self._manifesto_checado(m, manual))
        worker.erro.connect(lambda m: self._manifesto_erro(m, manual))
        self._updater_worker = worker
        worker.finished.connect(
            lambda: setattr(self, "_updater_worker", None))
        worker.start()

    def _manifesto_checado(self, manifesto, manual: bool):
        if manifesto is None:
            if manual:
                self._on_status(
                    f"Você está na versão mais recente (v{APP_VERSION})",
                    "success")
            return
        self._manifesto_pendente = manifesto
        self._mostrar_banner_atualizacao(manifesto)
        if manual:
            self._on_status(
                f"Atualização disponível: v{manifesto.versao}", "accent")

    def _manifesto_erro(self, motivo: str, manual: bool):
        if manual:
            self._on_status(f"Falha ao verificar: {motivo}", "danger")

    # ---------------- banner ----------------

    def _mostrar_banner_atualizacao(self, manifesto):
        if self.banner_update is not None:
            try:
                self.banner_update.setParent(None)
                self.banner_update.deleteLater()
            except RuntimeError:
                pass
            self.banner_update = None
        banner = BannerAtualizacao(manifesto, self)
        banner.atualizar.connect(self._atualizar_agora)
        banner.adiar.connect(self._adiar_atualizacao)
        banner.ver_notas.connect(self._mostrar_notas_atualizacao)
        banner.set_bloqueado(self._host_ocupado())
        root = self.centralWidget()
        if root is None or root.layout() is None:
            return
        root.layout().insertWidget(1, banner)
        self.banner_update = banner

    def _esconder_banner_atualizacao(self):
        if self.banner_update is None:
            return
        try:
            self.banner_update.setParent(None)
            self.banner_update.deleteLater()
        except RuntimeError:
            pass
        self.banner_update = None
        self._manifesto_pendente = None

    def _adiar_atualizacao(self):
        m = self._manifesto_pendente
        if not m:
            return
        cfg = updater.carregar_config()
        nova = updater.Config(
            ultima_checagem=cfg.ultima_checagem,
            versao_ignorada=m.versao,
            ignorada_ate=time.strftime(
                "%Y-%m-%dT%H:%M:%S",
                time.localtime(time.time() + 24 * 3600)),
            url_manifesto=cfg.url_manifesto,
        )
        updater.salvar_config(nova)
        self._esconder_banner_atualizacao()
        self._on_status(
            f"Atualização para v{m.versao} adiada por 24 h", "muted")

    def _mostrar_notas_atualizacao(self):
        m = self._manifesto_pendente
        if not m:
            return
        texto = m.notas or "(o release não publicou notas)"
        QMessageBox.information(self, f"Novidades na v{m.versao}", texto)

    # ---------------- download + aplicar ----------------

    def _atualizar_agora(self):
        m = self._manifesto_pendente
        if not m:
            return
        if self._host_ocupado():
            self._on_status(
                "Termine o envio / agente / fila antes de atualizar", "danger")
            return
        if self._download_worker is not None and self._download_worker.isRunning():
            return
        self._on_status(f"Baixando v{m.versao}…", "accent")
        worker = DownloadWorker(m)
        worker.progresso.connect(self._progresso_download)
        worker.ok.connect(self._download_pronto)
        worker.erro.connect(self._download_erro)
        self._download_worker = worker
        worker.finished.connect(
            lambda: setattr(self, "_download_worker", None))
        worker.start()

    def _progresso_download(self, baixado: int, total: int):
        if self.banner_update is not None:
            try:
                self.banner_update.set_progresso(baixado, total)
            except RuntimeError:
                pass
        if total > 0:
            pct = int(baixado * 100 / total)
            self._on_status(f"Baixando atualização… {pct}%", "accent")
        else:
            self._on_status(
                f"Baixando atualização… {baixado // 1024} KB", "accent")

    def _download_pronto(self, caminho: str):
        try:
            updater.aplicar(Path(caminho), relaunch=True)
        except updater.ManifestoErro as e:
            self._on_status(f"Falha ao aplicar: {e.motivo}", "danger")
            return
        self._on_status("Aplicando atualização… o app vai reiniciar", "accent")
        QTimer.singleShot(400, QApplication.quit)

    def _download_erro(self, motivo: str):
        self._on_status(f"Falha no download: {motivo}", "danger")
        if self.banner_update is not None:
            try:
                self.banner_update.set_erro(motivo)
            except RuntimeError:
                pass

    # ---------------- URL de atualização ----------------

    def _configurar_url_atualizacao(self):
        cfg = updater.carregar_config()
        atual = cfg.url_manifesto or updater.URL_MANIFESTO_PADRAO
        novo, ok = QInputDialog.getText(
            self, "URL de atualização",
            "Endereço do manifest.json. Deixe em branco para desativar a "
            "checagem automática:",
            text=atual)
        if not ok:
            return
        novo = novo.strip()
        if novo and updater.eh_placeholder(novo):
            self._on_status(
                "A URL ainda tem SEU_USUARIO; troque pelo repositório real.",
                "danger")
            return
        nova = updater.Config(
            ultima_checagem=cfg.ultima_checagem,
            versao_ignorada=cfg.versao_ignorada,
            ignorada_ate=cfg.ignorada_ate,
            url_manifesto=novo,
        )
        if updater.salvar_config(nova):
            self._on_status("URL de atualização salva", "success")
            self._checar_atualizacao(manual=True)
        else:
            self._on_status("Não consegui salvar a URL", "danger")

    # ---------------- helpers ----------------

    def _host_ocupado(self) -> bool:
        """`_ocupado` é opcional no host; se não existir, trata como livre."""
        fn = getattr(self, "_ocupado", None)
        if callable(fn):
            try:
                return bool(fn())
            except Exception:
                return False
        return False

    # ---------------- integração com host ----------------

    def _atualizar_banner_bloqueado(self):
        """O host pode chamar isto em `_atualizar_controles_ocupado`.

        Opcional: se o host não chamar, o banner continua funcional, só não
        reflete em tempo real o estado de ocupado.
        """
        if self.banner_update is None:
            return
        try:
            self.banner_update.set_bloqueado(self._host_ocupado())
        except RuntimeError:
            pass
