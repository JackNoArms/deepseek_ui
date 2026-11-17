"""DeepSeek UI — ponto de entrada.

UI local mínima que fala com o chat.deepseek.com por automação de navegador:
manda perguntas, recebe respostas e mexe nos controles da página (modo,
DeepThink, Search, nova conversa, trocar de conversa).

Na versão instalada (empacotada pelo PyInstaller, sem console) a saída vai
para `logs/deepseek_ui.log` na pasta de dados e, na primeira execução, o app
oferece trazer login e configurações de uma cópia do código-fonte.

`--verificar` abre a janela, roda o autoteste (`src/autoteste.py`: recursos,
plataforma da janela, shell, painel do celular, Chrome) e fecha; o código de
saída é o número de falhas. `--sem-chrome` pula o Chrome.
"""

import sys
from pathlib import Path

from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QFont, QIcon
from PyQt6.QtWidgets import QApplication, QFileDialog, QMessageBox

from src import caminhos
from src.__version__ import __version__

LOG_MAX_BYTES = 2_000_000


def _log_em_arquivo():
    """Sem console, `print` e tracebacks iriam para lugar nenhum."""
    if sys.stdout is not None and sys.stderr is not None:
        return
    log = caminhos.pasta_logs() / "deepseek_ui.log"
    try:
        if log.exists() and log.stat().st_size > LOG_MAX_BYTES:
            log.replace(log.with_suffix(".log.1"))
        arquivo = open(log, "a", encoding="utf-8", buffering=1)
    except OSError:
        return
    sys.stdout = sys.stdout or arquivo
    sys.stderr = sys.stderr or arquivo
    print(f"--- DeepSeek UI {__version__} ---")


def _copias_sugeridas() -> list[Path]:
    """Cópias do código-fonte em Documentos, a mais usada recentemente primeiro."""
    docs = Path.home() / "Documents"
    try:
        pastas = [p for p in docs.iterdir()
                  if p.is_dir() and caminhos.parece_copia_do_app(p)]
    except OSError:
        return []

    def uso(pasta):
        perfil = pasta / "chrome_profile"
        try:
            return (perfil if perfil.exists() else pasta).stat().st_mtime
        except OSError:
            return 0

    return sorted(pastas, key=uso, reverse=True)


def _oferecer_importacao():
    """Primeira execução instalada: trazer login e config de uma cópia antiga."""
    if not caminhos.empacotado() or "--verificar" in sys.argv:
        return
    marca = caminhos.pasta_dados() / "primeira_execucao.ok"
    if marca.exists():
        return
    try:
        marca.write_text(__version__, encoding="utf-8")
    except OSError:
        pass
    if caminhos.pasta_perfil_chrome().exists() or caminhos.arquivo_config().exists():
        return

    sugestoes = _copias_sugeridas()
    caixa = QMessageBox()
    caixa.setWindowTitle("DeepSeek UI — primeira execução")
    caixa.setIcon(QMessageBox.Icon.Question)
    texto = ("Quer trazer o login do DeepSeek, o pareamento do celular e as "
             "configurações de uma cópia do DeepSeek UI que você já usa?\n\n"
             "Nada é apagado na cópia antiga.")
    if sugestoes:
        texto += f"\n\nEncontrei: {sugestoes[0]}"
    caixa.setText(texto)
    usar = (caixa.addButton("Trazer desta pasta", QMessageBox.ButtonRole.AcceptRole)
            if sugestoes else None)
    escolher = caixa.addButton("Escolher outra pasta…", QMessageBox.ButtonRole.ActionRole)
    caixa.addButton("Começar do zero", QMessageBox.ButtonRole.RejectRole)
    caixa.exec()

    origem = None
    if usar is not None and caixa.clickedButton() is usar:
        origem = sugestoes[0]
    elif caixa.clickedButton() is escolher:
        pasta = QFileDialog.getExistingDirectory(
            None, "Pasta da cópia antiga (a que tem o main.py)",
            str(Path.home() / "Documents"))
        origem = Path(pasta) if pasta else None
    if origem is None:
        return
    if not caminhos.parece_copia_do_app(origem):
        QMessageBox.warning(None, "DeepSeek UI",
                            "Essa pasta não parece uma cópia do DeepSeek UI "
                            "(precisa ter o main.py e o chrome_profile ou o "
                            ".workspace.json). Começando do zero.")
        return
    trazidos = caminhos.importar_de(origem)
    print(f"Importado de {origem}: {', '.join(trazidos) or 'nada novo'}")


def main():
    _log_em_arquivo()
    app = QApplication(sys.argv)
    app.setApplicationName("DeepSeek UI")
    app.setApplicationDisplayName("DeepSeek UI")
    app.setApplicationVersion(__version__)
    app.setFont(QFont("Segoe UI", 10))

    from src.project import carregar_tema
    from src.theme import aplicar_tema, stylesheet

    aplicar_tema(carregar_tema())
    app.setStyleSheet(stylesheet())
    favicon = caminhos.recurso("assets", "favicon.png")
    if favicon.is_file():
        app.setWindowIcon(QIcon(str(favicon)))

    _oferecer_importacao()

    from src.window import MainWindow

    window = MainWindow()
    if favicon.is_file():
        window.setWindowIcon(QIcon(str(favicon)))
    window.show()
    if "--verificar" in sys.argv:
        def concluir():
            from src.autoteste import rodar_autoteste
            print(f"verificar: DeepSeek UI {__version__} "
                  f"recursos={caminhos.raiz_recursos()} dados={caminhos.pasta_dados()}")
            falhas = rodar_autoteste(app, com_chrome="--sem-chrome" not in sys.argv)
            window.close()
            app.exit(falhas)
        QTimer.singleShot(1500, concluir)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
