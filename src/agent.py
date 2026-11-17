"""O loop agêntico: enviar → parsear → executar → realimentar → repetir.

O DeepSeek web não tem tool-calling. O ciclo é simulado: o modelo escreve o que
quer fazer, o app executa e cola o resultado como a próxima mensagem. Isso muda
o desenho em três pontos:

  • **Round trip é caro** (10–60s). Por isso todas as leituras que ele pedir numa
    resposta são atendidas de uma vez, numa mensagem só.
  • **Leituras e escritas são controladas pela política.** Por padrão, cada
    leitura pede consentimento antes de compartilhar dados; escrita e comando
    passam pela confirmação definida no perfil de acesso.
  • **Tem que ter fim.** O agente segue até o modelo concluir ou o usuário
    parar; um limite opcional pode ser definido por quem o instancia.

O agente **não toca em Qt**. Ele avisa o que está acontecendo por callbacks, e
quem chama decide como mostrar. As confirmações são callbacks síncronos que
rodam na thread da GUI via sinal bloqueante.

**Habilidades (skills).** O agente aceita um provedor de habilidades em
``habilidades`` (lista, callable ou objeto com ``.all()``). A resolução acontece
no início de cada ``rodar`` — o próximo turno do usuário reflete o que o
usuário ativou/desativou na aba Habilidades. ``realimentar`` não reenvia o
bloco de skills (o modelo já o viu no início do turno).
"""

from dataclasses import dataclass, field
import time

from src.executor import Executor, relatorio
from src.parser import Resposta, parse
from src.prompts import montar, realimentar
from src.sandbox import SandboxError
from src.wrapper import ErroTamanho

MAX_ERROS_FORMATO_CONSECUTIVOS = 4
# Só para captura pelo DOM. Quando o texto veio da API do site ele já é o que o
# servidor guardou; reler não muda nada.
MAX_RECAPTURAS_RESPOSTA = 4


@dataclass
class Passo:
    """Uma rodada do loop, para a timeline da UI."""

    n: int
    resposta: str = ""
    resumo: str = ""
    leituras: list[str] = field(default_factory=list)
    escritas: list[str] = field(default_factory=list)
    comandos: list[str] = field(default_factory=list)
    nota: str = ""


class Agente:
    """Conduz a tarefa até o modelo dizer `acao=fim` ou o usuário parar."""

    def __init__(self, controller, project, callbacks, max_iteracoes=None,
                 instrucoes="", formato="markdown", incluir_mapa=True,
                 anexos=None, arquivos=None, habilidades=None):
        self.controller = controller
        self.project = project
        self.cb = callbacks
        self.max_iteracoes = max_iteracoes
        self.instrucoes = instrucoes
        self.formato = formato
        self.incluir_mapa = incluir_mapa
        self.anexos = anexos or []
        self.arquivos = list(arquivos or [])
        self.habilidades = habilidades
        self._parar = False
        self.passos: list[Passo] = []

    def parar(self):
        """Pedido de parada. O loop sai no fim da rodada atual."""
        self._parar = True

    # ---------------- habilidades ----------------

    def _resolver_habilidades(self):
        """Normaliza ``self.habilidades`` em lista de skills (ou None).

        Aceita três formas, para o chamador não precisar saber qual foi usada:
        ``None``, lista iterável, ou objeto com ``.all()`` (o ``SkillsRepo``) —
        callables também são aceitos, para reload preguiçoso.
        """
        h = self.habilidades
        if h is None:
            return None
        all_method = getattr(h, "all", None)
        if callable(all_method):
            return list(all_method())
        if callable(h):
            return list(h())
        return list(h)

    # ---------------- ciclo ----------------

    def rodar(self, pedido: str, primeira: bool = True):
        mensagem = montar(
            pedido, project=self.project, primeira=primeira, agente=True,
            instrucoes=self.instrucoes, formato=self.formato,
            incluir_mapa=self.incluir_mapa, anexos=self.anexos,
            habilidades=self._resolver_habilidades())

        erros_formato_consecutivos = 0
        n = 0
        while True:
            if self.max_iteracoes is not None and n >= self.max_iteracoes:
                self._aviso(f"Teto de {self.max_iteracoes} rodadas atingido. "
                            "Peça para continuar se ainda faltar.")
                return
            n += 1
            if self._parar:
                self._aviso("Parado por você.")
                return
            passo = Passo(n=n)
            self.passos.append(passo)

            try:
                if self.arquivos:
                    resposta = self.controller.send_message(
                        mensagem, on_update=self.cb.parcial,
                        arquivos=self.arquivos,
                        on_sent=lambda: self.cb.passo_inicio(passo))
                    self.arquivos = []
                else:
                    resposta = self.controller.send_message(
                        mensagem, on_update=self.cb.parcial,
                        on_sent=lambda: self.cb.passo_inicio(passo))
            except ErroTamanho as erro:
                if erro.lado == "envio":
                    self._erro_no_passo(passo, f"Envio cortado pelo DeepSeek: {erro}")
                    self._aviso(
                        f"Tarefa interrompida: {erro} Nada foi reenviado. Com "
                        "a conversa muito longa, comece uma nova; com um "
                        "arquivo enorme, peça ao modelo para buscar trechos.")
                    return
                passo.resposta = erro.parcial
                self._erro_no_passo(passo, f"Resposta cortada pelo DeepSeek: {erro}")
                if self._parar:
                    self._aviso("Parado por você.")
                    return
                erros_formato_consecutivos += 1
                if erros_formato_consecutivos >= MAX_ERROS_FORMATO_CONSECUTIVOS:
                    self._aviso(
                        f"Tarefa interrompida após {erros_formato_consecutivos} "
                        "respostas inválidas ou cortadas seguidas. Última: "
                        f"{erro}")
                    return
                mensagem = realimentar(
                    f"Sua última resposta passou do limite de saída do "
                    f"DeepSeek e foi cortada ({erro}). Nada dela foi aplicado. "
                    "Refaça em partes menores: no máximo um arquivo por "
                    "resposta e, se o arquivo for grande, divida a tarefa em "
                    "etapas.",
                    formato=self.formato, agente=True)
                continue
            passo.resposta = resposta or ""
            lido = parse(passo.resposta, formato=self.formato)
            captura = getattr(self.controller, "ultima_captura", None) or {}
            capturada_do_servidor = captura.get("fonte") == "api"
            if (not lido.valida and self.formato in ("json", "xml")
                    and not capturada_do_servidor):
                extrair_novamente = getattr(
                    self.controller, "extract_last_response", None)
                if callable(extrair_novamente):
                    for _ in range(MAX_RECAPTURAS_RESPOSTA):
                        time.sleep(0.4)
                        resposta_atual = extrair_novamente()
                        if resposta_atual and resposta_atual != passo.resposta:
                            passo.resposta = resposta_atual
                            lido = parse(passo.resposta, formato=self.formato)
                            if lido.valida:
                                break
            if lido.valida and self.formato in ("json", "xml"):
                pedidos = sum(a.verbo in ("ler", "listar", "buscar")
                              for a in lido.acoes)
                if pedidos > 1:
                    lido.valida = False
                    lido.erro = (
                        "o modo Agente estruturado aceita um pedido de "
                        "leitura/listagem/busca por resposta")
                    lido.acoes = []
                    lido.resumo = f"Resposta {self.formato.upper()} inválida: {lido.erro}"
            passo.resumo = lido.resumo
            self.cb.resposta(passo, lido)

            if self._parar:
                self._aviso("Parado por você.")
                return
            if not lido.valida:
                erros_formato_consecutivos += 1
                if erros_formato_consecutivos >= MAX_ERROS_FORMATO_CONSECUTIVOS:
                    self._aviso(
                        f"Tarefa interrompida após {erros_formato_consecutivos} "
                        f"respostas {self.formato.upper()} inválidas consecutivas. "
                        "Não enviei outra correção; confira a última resposta e "
                        "tente novamente.")
                    return
                if capturada_do_servidor:
                    origem = (
                        "O texto analisado é exatamente o que o DeepSeek "
                        "guardou da sua resposta, então o problema está no "
                        "conteúdo, não na captura; corrija a sintaxe e")
                else:
                    origem = (
                        "Isso também pode acontecer se a captura da resposta "
                        "tiver vindo incompleta; não altere as ações nem os "
                        "arquivos, apenas")
                mensagem = realimentar(
                    f"O app não conseguiu interpretar como {self.formato.upper()} "
                    f"o conteúdo que recebeu: {lido.erro}. {origem} reenvie o "
                    "objeto completo no protocolo solicitado.",
                    formato=self.formato, agente=True)
                continue

            erros_formato_consecutivos = 0
            verbos = {a.verbo for a in lido.acoes}
            # 'fim' junto com pedido de informação NÃO encerra: o modelo às vezes
            # fecha por reflexo antes de ter visto o que pediu. Encerrar ali
            # faria a leitura acontecer e o resultado morrer sem ser entregue.
            pediu_info = bool(verbos & {"ler", "listar", "buscar"})

            if "fim" in verbos and not pediu_info and not (
                    verbos & {"criar", "modificar", "apagar"}):
                self._aviso("Tarefa concluída pela Kitty.")
                return

            retorno = self._executar(lido, passo)

            if self._parar:
                self._aviso("Parado por você.")
                return
            if retorno is None:
                # Nada para fazer e nem 'fim': o modelo parou de colaborar.
                if lido.suspeita:
                    self._aviso("Veio código sem alvo. Revise na mão.")
                else:
                    self._aviso("Sem mais ações; encerrando.")
                return

            # Depois de escrever, 'fim' vale. Depois de LER, não: o modelo ainda
            # não viu o conteúdo, então tem que receber a próxima mensagem.
            if "fim" in verbos and not pediu_info:
                self._aviso("Tarefa concluída pela Kitty.")
                return

            mensagem = retorno

    # ---------------- execução de um turno ----------------

    def _executar(self, lido, passo: Passo) -> str | None:
        """Faz o que a resposta pediu. Devolve a próxima mensagem, ou None se acabou."""
        decisoes = [a for a in lido.acoes if a.verbo == "decidir"]
        if decisoes:
            decisao = decisoes[0]
            escolha = self.cb.confirmar_decisao(decisao)
            arquivos = []
            if isinstance(escolha, tuple):
                escolha, arquivos = escolha
            if not escolha:
                return None
            # Imagem/arquivo da resposta livre sobe junto da próxima rodada.
            self.arquivos = [c for c in (arquivos or []) if c]
            return realimentar(
                f"Decisão do usuário para “{decisao.extras['pergunta']}”: "
                f"{escolha}. Continue a tarefa com essa escolha.",
                formato=self.formato, agente=True)

        leituras, relatorios = [], []
        fez_algo = False

        # 1. olhar o projeto (ler, listar, buscar): tudo automático.
        # Na ORDEM em que o modelo pediu — ele encadeia o raciocínio nela.
        # Sem teto de quantidade nem de tamanho: se a mensagem passar do que o
        # site aceita, o envio acusa `ErroTamanho` com os números.
        pedidos = [a for a in lido.acoes if a.verbo in ("ler", "listar", "buscar")]

        for acao in pedidos:
            fez_algo = True
            rel = acao.caminho or ""
            if acao.verbo == "buscar":
                termo = (acao.extras.get("termo") or acao.extras.get("term")
                         or acao.extras.get("q") or "")
                descricao = f"busca por '{termo}'"
                if rel:
                    descricao += f" em {rel}"
            elif acao.verbo == "listar":
                descricao = f"listagem de {rel or self.project.nome}"
            else:
                descricao = rel
            if self.project.permissions.requires_read_confirmation:
                if not self.cb.confirmar_leitura(acao, descricao):
                    relatorios.append(
                        f"· {descricao or 'leitura'} recusada; nenhum conteúdo "
                        "foi enviado ao DeepSeek")
                    passo.nota = "leitura recusada"
                    continue
            try:
                if acao.verbo == "listar":
                    conteudo = self.project.listar(rel)
                    rel = f"árvore de {rel or self.project.nome}"
                elif acao.verbo == "buscar":
                    termo = (acao.extras.get("termo") or acao.extras.get("term")
                             or acao.extras.get("q") or "")
                    conteudo = self.project.buscar(
                        termo, em=rel or None, ext=acao.extras.get("ext"))
                    rel = f"busca por '{termo}'" + (f" em {rel}" if rel else "")
                else:
                    conteudo = self.project.ler(rel)

                leituras.append((rel, conteudo))
                passo.leituras.append(rel)
                self.cb.leitura(rel)
            except (SandboxError, OSError) as e:
                relatorios.append(f"✗ {acao.verbo} {rel}: {e}")
                passo.leituras.append(f"{rel} (falhou)")

        # 2. escrita: a UI confirma ou o perfil autoriza antes de devolver planos.
        acoes_escrita = [a for a in lido.acoes
                         if a.verbo in ("criar", "modificar", "apagar")]
        if acoes_escrita:
            fez_algo = True
            executor = Executor(self.project)
            planos = executor.preparar(acoes_escrita)
            escolhidos = self.cb.confirmar_escrita(planos)
            if escolhidos:
                resultados = executor.aplicar(escolhidos)
                relatorios.append(relatorio(resultados))
                passo.escritas = [r.plano.rel for r in resultados
                                  if r.status == "aplicado"]
                nao_autorizados = [
                    plano for plano in planos
                    if plano.aplicavel and plano not in escolhidos
                ]
                if nao_autorizados:
                    relatorios.append(
                        "· Estas alterações não foram selecionadas para aplicação: "
                        + ", ".join(plano.rel for plano in nao_autorizados)
                        + ". Elas não foram aplicadas.")
                self.cb.escrita_aplicada(resultados)
            else:
                autorizaveis = [plano.rel for plano in planos if plano.aplicavel]
                if autorizaveis:
                    relatorios.append(
                        "· Nenhuma alteração foi selecionada para aplicação: "
                        + ", ".join(autorizaveis)
                        + "."
                    )
                    passo.nota = "alterações não selecionadas"
            bloqueados = [plano for plano in planos if not plano.aplicavel]
            for plano in bloqueados:
                relatorios.append(
                    f"✗ {plano.rel}: ação bloqueada pelo app — {plano.erro}")

        # 3. comandos: a UI aplica o perfil de Acesso e roda no shell (ADR-022).
        comandos = [a for a in lido.acoes if a.verbo == "rodar"]
        if comandos:
            fez_algo = True
            saida = self.cb.confirmar_comando(comandos)
            if saida:
                relatorios.append(saida)
                passo.comandos = [(a.conteudo or "").strip().split("\n")[0]
                                  for a in comandos]
            else:
                relatorios.append("✗ O usuário não autorizou rodar o comando.")
                passo.nota = "comando recusado"

        if not fez_algo:
            return None
        return realimentar(
            "\n".join(relatorios), leituras,
            formato=self.formato, agente=True)

    def _erro_no_passo(self, passo: Passo, resumo: str):
        """Fecha a bolha da rodada com o erro, sem ações para executar."""
        passo.resumo = resumo
        self.cb.resposta(passo, Resposta(valida=False, erro=resumo, resumo=resumo))

    def _aviso(self, texto: str):
        self.cb.fim(texto)


class Callbacks:
    """O que o agente precisa do mundo de fora. Sobrescreva o que usar."""

    def passo_inicio(self, passo): ...
    def parcial(self, texto): ...
    def resposta(self, passo, lido): ...
    def leitura(self, rel): ...
    def confirmar_escrita(self, planos):
        """Devolve os planos aprovados (lista vazia = recusou tudo)."""
        return []
    def escrita_aplicada(self, resultados): ...
    def confirmar_leitura(self, acao, descricao):
        """Autoriza o envio do resultado de leitura ao modelo."""
        return True
    def confirmar_comando(self, acoes):
        """Devolve a saída do comando, ou '' se não autorizou."""
        return ""
    def confirmar_decisao(self, acao):
        """Devolve a escolha do usuário ou None para interromper o agente.

        Com anexo na resposta livre, devolve ``(escolha, [caminhos])``.
        """
        return None
    def fim(self, motivo): ...
