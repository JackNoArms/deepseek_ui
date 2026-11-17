"""Diálogo de revisão: o que vai mudar no disco, antes de mudar.

Uma lista de planos à esquerda com caixa de marcar, o diff colorido à direita.
Nada é gravado até você clicar em Aplicar — e só o que estiver marcado.
"""

import html

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QSplitter,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from src.theme import Color, MONO

def _cores() -> dict:
    """Fundo e texto por marca de linha, no tema ativo."""
    return {
        "+": (Color.DIFF_ADD_BG, Color.DIFF_ADD_FG),   # adicionado
        "-": (Color.DIFF_DEL_BG, Color.DIFF_DEL_FG),   # removido
        "@": (Color.SURFACE, Color.TEXT_DIM),          # cabeçalho de trecho
    }


def diff_html(diff: str) -> str:
    if not diff:
        return f'<div style="color:{Color.TEXT_MUTED}">Sem alterações.</div>'
    linhas = []
    cores = _cores()
    for linha in diff.split("\n"):
        texto = html.escape(linha) or "&nbsp;"
        marca = linha[:1]
        if linha.startswith(("+++", "---")):
            fundo, cor = Color.SURFACE, Color.TEXT_MUTED
        else:
            fundo, cor = cores.get(marca, (Color.CODE_BG, Color.CODE_TEXT))
        linhas.append(
            f'<div style="background:{fundo};color:{cor};padding:1px 6px;'
            f'white-space:pre">{texto}</div>')
    return (f'<div style="font-family:{MONO};font-size:12px;line-height:1.45">'
            + "".join(linhas) + "</div>")


class DiffDialog(QDialog):
    """Revisa os planos e devolve os que foram marcados."""

    def __init__(self, planos, parent=None):
        super().__init__(parent)
        self.planos = planos
        self.setWindowTitle("Revisar alterações")
        self.resize(940, 620)

        lay = QVBoxLayout(self)
        lay.setSpacing(10)

        aplicaveis = sum(1 for p in planos if p.aplicavel)
        topo = QLabel(
            f"{aplicaveis} de {len(planos)} alteração(ões) selecionáveis. "
            "Confira os avisos e marque o que deseja aplicar.")
        topo.setWordWrap(True)
        lay.addWidget(topo)

        split = QSplitter(Qt.Orientation.Horizontal)

        self.lista = QListWidget()
        self.lista.setMinimumWidth(300)
        for plano in planos:
            item = QListWidgetItem(self._rotulo(plano))
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            marcavel = plano.aplicavel
            marcado = marcavel and not plano.provavel_truncamento
            item.setCheckState(Qt.CheckState.Checked if marcado
                               else Qt.CheckState.Unchecked)
            if not marcavel:
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsUserCheckable)
                item.setForeground(Qt.GlobalColor.gray)
            item.setData(Qt.ItemDataRole.UserRole, plano)
            if plano.avisos or plano.erro:
                item.setToolTip("\n".join(plano.avisos + ([plano.erro] if plano.erro else [])))
            self.lista.addItem(item)
        self.lista.currentRowChanged.connect(self._mostrar)
        split.addWidget(self.lista)

        direita = QWidget()
        dir_lay = QVBoxLayout(direita)
        dir_lay.setContentsMargins(0, 0, 0, 0)
        dir_lay.setSpacing(6)

        self.aviso = QLabel()
        self.aviso.setWordWrap(True)
        self.aviso.setObjectName("dangerHint")
        self.aviso.hide()
        dir_lay.addWidget(self.aviso)

        self.visor = QTextBrowser()
        self.visor.setOpenExternalLinks(False)
        dir_lay.addWidget(self.visor, 1)
        split.addWidget(direita)
        split.setSizes([320, 620])
        lay.addWidget(split, 1)

        botoes = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel)
        self.btn_aplicar = botoes.addButton("Aplicar marcados",
                                            QDialogButtonBox.ButtonRole.AcceptRole)
        self.btn_aplicar.setObjectName("send")
        self.lista.itemChanged.connect(self._atualizar_botao_aplicar)
        self._atualizar_botao_aplicar()
        botoes.accepted.connect(self.accept)
        botoes.rejected.connect(self.reject)
        lay.addWidget(botoes)

        if planos:
            self.lista.setCurrentRow(0)

    def _atualizar_botao_aplicar(self, _item=None):
        self.btn_aplicar.setEnabled(bool(self.marcados()))

    @staticmethod
    def _rotulo(plano):
        if plano.erro:
            return f"✗  {plano.rel or plano.acao.caminho}  (recusado)"
        if plano.sem_efeito:
            return f"·  {plano.rel}  (sem efeito)"
        alerta = "⚠ " if plano.avisos else ""
        return f"{alerta}{plano.rotulo}"

    def _mostrar(self, linha):
        if linha < 0 or linha >= len(self.planos):
            return
        plano = self.planos[linha]
        recados = list(plano.avisos)
        if plano.erro:
            recados.insert(0, f"Recusado: {plano.erro}")
        if recados:
            self.aviso.setText(" · ".join(recados))
            self.aviso.setStyleSheet(
                f"color:{Color.DANGER if plano.erro else Color.WARNING};font-size:12px")
            self.aviso.show()
        else:
            self.aviso.hide()

        if plano.acao.verbo == "apagar":
            self.visor.setHtml(
                f'<div style="font-family:{MONO};font-size:12px;color:{Color.DANGER}">'
                f"O arquivo {html.escape(plano.rel)} vai sair do projeto.<br><br>"
                "Ele é movido para <code>.deepseek_ui/backups/</code>, então dá para "
                "recuperar.</div>")
        else:
            self.visor.setHtml(diff_html(plano.diff))

    def marcados(self):
        """Planos que ficaram marcados quando você clicou em Aplicar."""
        escolhidos = []
        for i in range(self.lista.count()):
            item = self.lista.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                escolhidos.append(item.data(Qt.ItemDataRole.UserRole))
        return escolhidos


def revisar(planos, parent=None):
    """Abre o diálogo. Devolve os planos marcados, ou [] se cancelou."""
    if not planos:
        return []
    dlg = DiffDialog(planos, parent)
    if dlg.exec() != QDialog.DialogCode.Accepted:
        return []
    return dlg.marcados()


class CommandDialog(QDialog):
    """Confirma a execução de comandos (perfis com confirmação).

    Não há mais recusa por conteúdo ([[ADR-022 Shell livre para o agente]]):
    tudo o que o modelo pediu aparece e pode ser autorizado. Comando com cara
    de destrutivo ganha ⚠ e o botão deixa de ser o padrão do Enter.
    """

    def __init__(self, comandos, cwd, parent=None):
        super().__init__(parent)
        from src.runner import destrutivo

        self.setWindowTitle("Rodar comando")
        self.resize(640, 380)
        lay = QVBoxLayout(self)

        lay.addWidget(QLabel(
            f"No shell do sistema, começando em <code>{html.escape(str(cwd))}</code>:"))

        self.validos = [texto for texto in comandos if (texto or "").strip()]
        perigoso = any(destrutivo(texto) for texto in self.validos)

        corpo = []
        for texto in self.validos:
            marca = "⚠ " if destrutivo(texto) else ""
            linhas = html.escape(texto).replace("\n", "<br>&nbsp;&nbsp;")
            corpo.append(f'<div style="color:{Color.TEXT};padding:3px 0">'
                         f"{marca}$ {linhas}</div>")
        visor = QTextBrowser()
        visor.setHtml(f'<div style="font-family:{MONO};font-size:12px">'
                      + "".join(corpo) + "</div>")
        lay.addWidget(visor, 1)

        if perigoso:
            alerta = QLabel("⚠ Esse comando pode apagar, instalar, publicar ou "
                            "forçar algo — e comando não tem backup nem desfazer. "
                            "Leia com atenção antes de autorizar.")
            alerta.setWordWrap(True)
            alerta.setObjectName("dangerHint")
            lay.addWidget(alerta)

        botoes = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        rotulo = "Rodar mesmo assim" if perigoso else "Rodar"
        self.btn_ok = botoes.addButton(rotulo, QDialogButtonBox.ButtonRole.AcceptRole)
        self.btn_ok.setObjectName("send")
        self.btn_ok.setEnabled(bool(self.validos))
        # Em comando perigoso o botão não é o padrão: evita autorizar no Enter.
        self.btn_ok.setDefault(not perigoso)
        botoes.accepted.connect(self.accept)
        botoes.rejected.connect(self.reject)
        lay.addWidget(botoes)


def confirmar_comandos(comandos, cwd, parent=None):
    """Mostra os comandos e devolve os autorizados, ou [] se recusou."""
    if not comandos:
        return []
    dlg = CommandDialog(comandos, cwd, parent)
    if dlg.exec() != QDialog.DialogCode.Accepted:
        return []
    return dlg.validos
