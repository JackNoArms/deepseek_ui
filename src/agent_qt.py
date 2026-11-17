"""Roda o `Agente` numa QThread e pede confirmação na thread da GUI.

O agente roda fora da GUI, mas as confirmações precisam abrir diálogos (que só
podem existir na thread da GUI) e **devolver** a resposta para continuar o loop.
Sinal do Qt não devolve valor.

A solução é o par sinal + `threading.Event`:

    thread do agente          thread da GUI
    --------------------      -------------------------
    emite `pedir_escrita`  →  abre o diálogo
    espera no Event           chama `responder(escolha)`
    lê `_resposta`         ←  grava o valor e libera o Event

``abortar()` existe para o caso de a janela fechar com o agente esperando: sem
``ele, a thread ficaria presa no Event para sempre.

**Habilidades.** ``habilidades`` é opcional e é repassado tal qual para
``Agente`` — aceita ``None``, lista, callable ou ``SkillsRepo``. O agente
resolve no início de cada ``rodar``; a view do usuário altera o repo, e o
próximo turno vê o estado novo.
"""

import threading

from PyQt6.QtCore import QThread, pyqtSignal

from src.agent import Agente, Callbacks


class AgentWorker(QThread, Callbacks):
    """Um turno completo do agente, do pedido até o fim."""

    passo_sig = pyqtSignal(object)
    parcial_sig = pyqtSignal(str)
    resposta_sig = pyqtSignal(object, object)
    leitura_sig = pyqtSignal(str)
    escrita_sig = pyqtSignal(object)
    pedir_leitura = pyqtSignal(object)
    pedir_escrita = pyqtSignal(object)    # list[Plano]
    pedir_comando = pyqtSignal(object)    # list[Acao]
    pedir_decisao = pyqtSignal(object)    # Acao
    fim_sig = pyqtSignal(str)

    def __init__(self, controller, project, pedido, primeira, max_iteracoes=None,
                 instrucoes="", formato="markdown", incluir_mapa=True,
                 anexos=None, arquivos=None, habilidades=None):
        super().__init__()
        self.pedido = pedido
        self.primeira = primeira
        self._evento = threading.Event()
        self._resposta = None
        self._abortado = False
        extras = {} if max_iteracoes is None else {"max_iteracoes": max_iteracoes}
        self.agente = Agente(
            controller, project, self, instrucoes=instrucoes, formato=formato,
            incluir_mapa=incluir_mapa,
            anexos=anexos, arquivos=arquivos,
            habilidades=habilidades,
            **extras)

    # ---------------- thread ----------------

    def run(self):
        try:
            self.agente.rodar(self.pedido, primeira=self.primeira)
        except Exception as e:                      # o loop nunca derruba a GUI
            self.fim_sig.emit(f"Erro no agente: {e}")

    def parar(self):
        self.agente.parar()

    def abortar(self):
        """Libera quem estiver esperando confirmação (janela fechando)."""
        self._abortado = True
        self.agente.parar()
        self._resposta = None
        self._evento.set()

    def responder(self, valor):
        """Chamado pela GUI com o resultado da confirmação."""
        self._resposta = valor
        self._evento.set()

    def _perguntar(self, sinal, carga, vazio):
        if self._abortado:
            return vazio
        self._resposta = None
        self._evento.clear()
        sinal.emit(carga)
        self._evento.wait()
        return vazio if self._resposta is None else self._resposta

    # ---------------- Callbacks (rodam na thread do agente) ----------------

    def passo_inicio(self, passo):
        self.passo_sig.emit(passo)

    def parcial(self, texto):
        self.parcial_sig.emit(texto)

    def resposta(self, passo, lido):
        self.resposta_sig.emit(passo, lido)

    def leitura(self, rel):
        self.leitura_sig.emit(rel)

    def escrita_aplicada(self, resultados):
        self.escrita_sig.emit(resultados)

    def confirmar_leitura(self, acao, descricao):
        return self._perguntar(
            self.pedir_leitura, (acao, descricao), False)

    def confirmar_escrita(self, planos):
        return self._perguntar(self.pedir_escrita, planos, [])

    def confirmar_comando(self, acoes):
        return self._perguntar(self.pedir_comando, acoes, "")

    def confirmar_decisao(self, acao):
        return self._perguntar(self.pedir_decisao, acao, None)

    def fim(self, motivo):
        self.fim_sig.emit(motivo)
