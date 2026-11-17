"""Diálogo de controle remoto: status do Tailscale Serve, URL com token.

Não abre nada sozinho; mostra o estado atual e oferece o que fazer. O botão
`Ativar / Reiniciar` dispara o `.bat` com UAC — é a única ação deste diálogo
que mexe no sistema, e ela é irreversível de dentro do app (só o usuário
aceita o UAC). Todo o resto é leitura.

Um `QTimer` de 2,5 s relê o `serve status`: se o usuário aceitar o UAC numa
outra janela, o diálogo se atualiza sozinho quando a configuração ficar de pé.
"""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt, QTimer, QUrl
from PyQt6.QtGui import QDesktopServices, QGuiApplication
from PyQt6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)

from src.remote_ui import (
    encontrar_tailscale,
    habilitar_serve,
    ler_serve_status,
    ler_token,
    url_com_token,
)


class RemoteControlDialog(QDialog):
    """Estado do painel remoto + botões para configurar e copiar o link."""

    def __init__(self, parent, porta: int, token_path: str | Path,
                 bat_path: str | Path | None = None):
        super().__init__(parent)
        self.setObjectName("remoteDialog")
        self.setWindowTitle("Controle remoto")
        self.setMinimumWidth(620)
        self.porta = int(porta)
        self.token_path = Path(token_path)
        self.bat_path = Path(bat_path) if bat_path else None
        self.ts = encontrar_tailscale()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 14)
        layout.setSpacing(10)

        titulo = QLabel("CONTROLE REMOTO")
        titulo.setObjectName("decisionDialogTitle")
        layout.addWidget(titulo)

        self.lbl_ts = QLabel()
        self.lbl_ts.setWordWrap(True)
        self.lbl_ts.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(self.lbl_ts)

        caixa = QFrame()
        caixa.setObjectName("remoteStatusBox")
        caixa_lay = QVBoxLayout(caixa)
        caixa_lay.setContentsMargins(12, 10, 12, 10)
        caixa_lay.setSpacing(6)
        self.lbl_serve = QLabel()
        self.lbl_serve.setWordWrap(True)
        self.lbl_serve.setTextFormat(Qt.TextFormat.RichText)
        caixa_lay.addWidget(self.lbl_serve)

        self.campo_url = QLineEdit()
        self.campo_url.setObjectName("remoteUrl")
        self.campo_url.setReadOnly(True)
        self.campo_url.setPlaceholderText(
            "(o link aparece quando o serve estiver ativo)")
        caixa_lay.addWidget(self.campo_url)
        layout.addWidget(caixa)

        rodape = QHBoxLayout()
        rodape.setSpacing(8)
        self.btn_ativar = QPushButton("Ativar / Reiniciar")
        self.btn_ativar.setToolTip(
            "Roda configurar_tailscale.bat como Administrador (UAC). "
            "Configura uma vez por máquina.")
        self.btn_ativar.clicked.connect(self._ativar)
        rodape.addWidget(self.btn_ativar)
        self.btn_copiar = QPushButton("Copiar URL")
        self.btn_copiar.clicked.connect(self._copiar)
        rodape.addWidget(self.btn_copiar)
        self.btn_abrir = QPushButton("Abrir no navegador")
        self.btn_abrir.clicked.connect(self._abrir)
        rodape.addWidget(self.btn_abrir)
        rodape.addStretch(1)
        self.btn_fechar = QPushButton("Fechar")
        self.btn_fechar.clicked.connect(self.accept)
        rodape.addWidget(self.btn_fechar)
        layout.addLayout(rodape)

        self._atualizar()
        self._timer = QTimer(self)
        self._timer.setInterval(2500)
        self._timer.timeout.connect(self._atualizar)
        self._timer.start()

    # ---------------- estado ----------------

    def _atualizar(self):
        if self.ts is None:
            self.lbl_ts.setText(
                "❌ <b>Tailscale não encontrado.</b> Instale primeiro em "
                "tailscale.com/download/windows e faça login. Depois volte "
                "aqui e clique em <b>Ativar / Reiniciar</b>.")
            self.lbl_serve.setText("")
            self.campo_url.setText("")
            self.btn_ativar.setEnabled(False)
            self.btn_copiar.setEnabled(False)
            self.btn_abrir.setEnabled(False)
            return

        self.lbl_ts.setText(
            f"Tailscale: <code>{self.ts}</code> · painel local em "
            f"<code>http://127.0.0.1:{self.porta}</code>")
        self.btn_ativar.setEnabled(True)

        ativo, url = ler_serve_status(self.ts)
        if not ativo:
            self.lbl_serve.setText(
                "⚠ <b>Serve não configurado.</b> Clique em <b>Ativar / "
                "Reiniciar</b> — vai pedir permissão de Administrador (UAC) "
                "e configurar uma vez. Depois disso, a URL aparece aqui.")
            self.campo_url.setText("")
            self.btn_copiar.setEnabled(False)
            self.btn_abrir.setEnabled(False)
            return

        token = ler_token(self.token_path)
        completa = url_com_token(url, token)
        if not token:
            self.lbl_serve.setText(
                f"✅ Serve ativo em <code>{url}</code>, mas o token do painel "
                "não foi encontrado. Abra o app uma vez para gerá-lo.")
            self.campo_url.setText("")
            self.btn_copiar.setEnabled(False)
            self.btn_abrir.setEnabled(False)
            return
        self.lbl_serve.setText(
            f"✅ <b>Serve ativo.</b> URL base: <code>{url}</code><br>"
            "No iPhone: abra no <b>Safari</b>, depois <b>Compartilhar → "
            "Adicionar à Tela de Início</b> e use o ícone. Só então toque em "
            "<b>Ativar notificações</b> dentro do painel.")
        self.campo_url.setText(completa)
        self.btn_copiar.setEnabled(True)
        self.btn_abrir.setEnabled(True)

    # ---------------- ações ----------------

    def _ativar(self):
        if self.ts is None:
            return
        self.btn_ativar.setEnabled(False)
        self.lbl_serve.setText(
            "⌛ Lançando o instalador elevado… aceite o UAC na janela que "
            "abriu. Quando terminar, este painel se atualiza sozinho.")
        ok = habilitar_serve(self.ts, self.porta, self.bat_path)
        if not ok:
            self.lbl_serve.setText(
                "❌ Não consegui lançar o processo elevado. Rode "
                "<code>configurar_tailscale.bat</code> como Administrador "
                "manualmente.")
        # Reabilita em 3 s; o timer de status cuida do resto.
        QTimer.singleShot(3000, lambda: self.btn_ativar.setEnabled(True))

    def _copiar(self):
        texto = self.campo_url.text().strip()
        if not texto:
            return
        QGuiApplication.clipboard().setText(texto)
        # Feedback curto no próprio botão — quem colou no celular precisa ver
        # que a cópia foi feita, não só que o clique foi registrado.
        self.btn_copiar.setText("Copiado ✓")
        QTimer.singleShot(1200, lambda: self.btn_copiar.setText("Copiar URL"))

    def _abrir(self):
        texto = self.campo_url.text().strip()
        if texto:
            QDesktopServices.openUrl(QUrl(texto))
