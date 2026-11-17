"""Transforma ação em mudança no disco — com freio em cada etapa.

Dois passos separados de propósito:

  `preparar(acoes)` → planos    **não escreve nada.** Valida caminho, lê o
                                arquivo atual, calcula diff e levanta avisos.
  `aplicar(planos)` → resultados grava apenas planos aprovados pela política e
                                autorizados pela UI.

A separação existe para a UI poder mostrar o diff antes de qualquer gravação, e
para o loop agêntico poder recusar um plano inteiro sem ter tocado no projeto.

Escrita é atômica: grava num temporário na MESMA pasta e troca com `os.replace`.
Isso fecha a janela entre validar o caminho e abrir o arquivo, e evita deixar
arquivo pela metade se faltar energia no meio.
"""

import difflib
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from src.backup import Backup
from src.parser import Acao
from src.sandbox import SandboxError

# Abaixo disso, a resposta provavelmente foi truncada pelo limite de tokens.
FATOR_TRUNCAMENTO = 0.5


@dataclass
class Plano:
    """O que vai acontecer com um arquivo, antes de acontecer."""

    acao: Acao
    rel: str = ""
    destino: Path | None = None
    existe: bool = False
    atual: str | None = None
    novo: str | None = None
    diff: str = ""
    adicionadas: int = 0
    removidas: int = 0
    avisos: list[str] = field(default_factory=list)
    erro: str = ""
    sem_efeito: bool = False
    provavel_truncamento: bool = False

    @property
    def aplicavel(self) -> bool:
        return not self.erro and not self.sem_efeito

    @property
    def aplicavel_automaticamente(self) -> bool:
        return self.aplicavel and not self.provavel_truncamento

    @property
    def rotulo(self) -> str:
        verbo = {"criar": "criar", "modificar": "editar", "apagar": "apagar"}.get(
            self.acao.verbo, self.acao.verbo)
        if self.acao.verbo == "apagar":
            return f"{verbo} {self.rel}"
        return f"{verbo} {self.rel}  +{self.adicionadas} −{self.removidas}"


@dataclass
class Resultado:
    plano: Plano
    status: str      # aplicado | ignorado | recusado | erro
    detalhe: str = ""


class Executor:
    def __init__(self, project):
        self.project = project
        self.sandbox = project.sandbox
        self.backup = Backup(project.root)

    # ---------------- passo 1: preparar (só leitura) ----------------

    def preparar(self, acoes: list[Acao]) -> list[Plano]:
        return [self._preparar_uma(a) for a in acoes if a.verbo in
                ("criar", "modificar", "apagar")]

    def _preparar_uma(self, acao: Acao) -> Plano:
        plano = Plano(acao=acao, rel=acao.caminho or "")
        try:
            destino = self.project.resolver(acao.caminho, acao.verbo)
        except SandboxError as e:
            plano.erro = str(e)
            return plano

        plano.destino = destino
        plano.rel = self.project.relativo(destino)
        plano.existe = destino.is_file()

        if acao.verbo == "apagar":
            if not plano.existe:
                plano.sem_efeito = True
                plano.avisos.append("Arquivo não existe; nada a apagar.")
            else:
                plano.avisos.append("Vai para o backup, dá para recuperar.")
            return plano

        novo = acao.conteudo or ""
        try:
            self.sandbox.check_size(novo, plano.rel)
        except SandboxError as e:
            plano.erro = str(e)
            return plano
        plano.novo = novo

        if plano.existe:
            try:
                plano.atual = destino.read_text(encoding="utf-8", errors="replace")
            except OSError as e:
                plano.erro = f"Não consegui ler o arquivo atual: {e}"
                return plano
        else:
            plano.atual = None

        # O modelo disse "modificar" mas o arquivo não existe: ou ele inventou o
        # caminho, ou errou o verbo. Vale avisar, não bloquear — criar é o que
        # ele provavelmente queria, e o diff mostra o arquivo inteiro.
        if acao.verbo == "modificar" and not plano.existe:
            plano.avisos.append(
                "O modelo disse 'modificar', mas o arquivo não existe. "
                "Confira se o caminho está certo — vai ser criado.")
        if acao.verbo == "criar" and plano.existe:
            plano.avisos.append("Já existe: o conteúdo atual será substituído.")

        if plano.atual is not None and plano.atual == novo:
            plano.sem_efeito = True
            plano.avisos.append("Conteúdo idêntico ao atual; nada muda.")
            return plano

        if plano.atual and len(novo) < len(plano.atual) * FATOR_TRUNCAMENTO:
            plano.provavel_truncamento = True
            plano.avisos.append(
                f"⚠ O novo tem menos da metade do tamanho do atual "
                f"({len(novo)} vs {len(plano.atual)} bytes). Pode ser resposta "
                f"truncada — leia o diff com atenção.")

        self._montar_diff(plano)
        return plano

    def _montar_diff(self, plano: Plano):
        antes = (plano.atual or "").splitlines(keepends=True)
        depois = (plano.novo or "").splitlines(keepends=True)
        linhas = list(difflib.unified_diff(
            antes, depois,
            fromfile=f"a/{plano.rel}" if plano.existe else "/dev/null",
            tofile=f"b/{plano.rel}", n=3))
        plano.diff = "".join(linhas)
        plano.adicionadas = sum(
            1 for l in linhas if l.startswith("+") and not l.startswith("+++"))
        plano.removidas = sum(
            1 for l in linhas if l.startswith("-") and not l.startswith("---"))

    # ---------------- passo 2: aplicar (escreve) ----------------

    def aplicar(self, planos: list[Plano]) -> list[Resultado]:
        """Grava planos autorizados. Tudo passa pelo backup antes."""
        aplicaveis = [p for p in planos if p.aplicavel]
        if aplicaveis:
            self.backup.novo_lote()

        resultados = []
        for plano in planos:
            if plano.erro:
                resultados.append(Resultado(plano, "recusado", plano.erro))
                continue
            if plano.sem_efeito:
                resultados.append(Resultado(
                    plano, "ignorado", plano.avisos[0] if plano.avisos else ""))
                continue
            if not plano.aplicavel:
                resultados.append(Resultado(
                    plano, "recusado", "; ".join(plano.avisos)
                    or "Plano não aplicável."))
                continue
            try:
                resultados.append(self._aplicar_um(plano))
            except (OSError, SandboxError) as e:
                resultados.append(Resultado(plano, "erro", str(e)))
        return resultados

    def _aplicar_um(self, plano: Plano) -> Resultado:
        # Revalida na hora de escrever: entre preparar e aplicar o usuário pode
        # ter trocado de pasta, ou o disco pode ter mudado.
        destino = self.project.resolver(plano.acao.caminho, plano.acao.verbo)

        if plano.acao.verbo == "apagar":
            movido = self.backup.mover(
                destino, self.project.caminho_backup(destino))
            return Resultado(plano, "aplicado",
                             f"apagado (cópia em {movido})" if movido else "não existia")

        if destino.is_file():
            self.backup.salvar(destino, self.project.caminho_backup(destino))
        destino.parent.mkdir(parents=True, exist_ok=True)
        self._escrever_atomico(destino, plano.novo or "")
        verbo = "criado" if not plano.existe else "atualizado"
        return Resultado(plano, "aplicado",
                         f"{verbo} (+{plano.adicionadas} −{plano.removidas})")

    @staticmethod
    def _escrever_atomico(destino: Path, conteudo: str):
        """Grava em temporário na mesma pasta e troca — nunca arquivo pela metade."""
        fd, tmp = tempfile.mkstemp(dir=str(destino.parent), prefix=".kitty-", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
                f.write(conteudo)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, destino)
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise


def relatorio(resultados: list[Resultado]) -> str:
    """Resumo em texto — serve para a UI e para realimentar o modelo na Fase 4."""
    if not resultados:
        return "Nada a aplicar."
    linhas = []
    for r in resultados:
        marca = {"aplicado": "✓", "ignorado": "·", "recusado": "✗", "erro": "✗"}.get(
            r.status, "?")
        linhas.append(f"{marca} {r.plano.rel or '?'} — {r.status}"
                      + (f": {r.detalhe}" if r.detalhe else ""))
    return "\n".join(linhas)
