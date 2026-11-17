"""Processos que continuam rodando depois da resposta ([[ADR-025 Comandos contínuos em segundo plano]]).

Por que existe: `runner.rodar` espera o comando terminar (até 5 min, ADR-023).
Um `npm run dev` não termina nunca, então o agente ficava parado até o tempo
esgotar e o servidor era derrubado no fim — e nenhum outro comando rodava nesse
meio-tempo. Aqui o comando sobe, o app espera só até ele **ficar pronto**
(endereço ou "ready" na saída, ou alguns segundos de silêncio depois de falar) e
devolve o controle. O processo segue vivo, com a saída num arquivo de log, até
alguém parar (botão, `@parar N`) ou o app fechar.

Sem Qt: a janela chama `esperar_pronto` numa thread e lê o log por timer.
"""

import codecs
import itertools
import os
import re
import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

from src.runner import _SEM_JANELA, ComandoRecusado, _decodificar, _preparar, encerrar

# Comandos que não terminam sozinhos. Lista conservadora: na dúvida, o comando
# roda do jeito normal; o modelo pode pedir segundo plano explicitamente.
_CONTINUO = [
    r"\b(npm|pnpm|yarn|bun)\s+(run\s+)?(dev|start|serve|watch|preview)\b",
    r"\bnpx\s+(vite|nodemon|serve|http-server|live-server|next\s+dev)\b",
    r"^\s*(vite|nodemon|http-server|live-server)\b",
    r"\bnext\s+(dev|start)\b",
    r"\bng\s+serve\b",
    r"\bwebpack(-dev-server|\s+serve)\b",
    r"\bpython[0-9.]*(\.exe)?\s+-m\s+http\.server\b",
    r"\b(uvicorn|gunicorn|hypercorn|daphne)\b",
    r"\bflask\s+run\b",
    r"\bmanage\.py\s+runserver\b",
    r"\bstreamlit\s+run\b",
    r"\bjupyter(-lab|\s+lab|\s+notebook)\b",
    r"\bdocker(-compose|\s+compose)\s+up\b(?!.*\s(-d|--detach)\b)",
    r"\btail\s+-f\b",
    r"\bping\b.*\s-t\b",
    r"\s--watch\b",
]
_CONTINUO_RE = [re.compile(p, re.IGNORECASE | re.MULTILINE) for p in _CONTINUO]

# Sinais de que o servidor subiu.
_PRONTO_RE = re.compile(
    r"https?://(localhost|127\.0\.0\.1|0\.0\.0\.0|\[::1?\]|[\w.-]+):\d+"
    r"|\b(ready|listening|compiled successfully|server running|running on"
    r"|watching for file changes|started server|serving http)\b",
    re.IGNORECASE)

# Comandos internos do app (não vão para o shell).
_INTERNO_RE = re.compile(r"^\s*@(processos|saida|saída|parar)\b\s*(\d+)?\s*$", re.IGNORECASE)

ESPERA_MAXIMA_PADRAO = 20.0
SILENCIO_PRONTO_PADRAO = 4.0
_VERDADEIRO = {"1", "true", "sim", "s", "yes", "y", "on"}


def e_continuo(comando: str) -> bool:
    """O comando parece não terminar sozinho (servidor, watch, tail -f)."""
    texto = comando or ""
    return any(r.search(texto) for r in _CONTINUO_RE)


def pediu_fundo(extras: dict | None) -> bool:
    """O modelo pediu segundo plano: `fundo=sim` (kitty) ou `background` (JSON/XML)."""
    for chave in ("fundo", "segundo_plano", "background", "bg"):
        valor = (extras or {}).get(chave)
        if valor is True or str(valor or "").strip().lower() in _VERDADEIRO:
            return True
    return False


def comando_interno(texto: str):
    """`@processos`, `@saida N`, `@parar N` → (nome, id ou None); senão None."""
    m = _INTERNO_RE.match(texto or "")
    if not m:
        return None
    nome = m.group(1).lower().replace("saída", "saida")
    return nome, (int(m.group(2)) if m.group(2) else None)


@dataclass
class Processo:
    id: int
    comando: str
    cwd: str
    proc: subprocess.Popen
    log: Path
    script: Path | None = None
    inicio: float = field(default_factory=time.monotonic)

    @property
    def pid(self) -> int:
        return self.proc.pid

    def vivo(self) -> bool:
        return self.proc.poll() is None

    @property
    def codigo(self):
        return self.proc.poll()

    def ler_bytes(self, pos: int) -> tuple[bytes, int]:
        """Bytes novos do log a partir de `pos` → (bytes, nova posição)."""
        try:
            with open(self.log, "rb") as f:
                f.seek(pos)
                dados = f.read()
        except OSError:
            return b"", pos
        return dados, pos + len(dados)

    def cauda(self, limite: int = 4000) -> str:
        """Final da saída, já decodificado."""
        try:
            tamanho = self.log.stat().st_size
            with open(self.log, "rb") as f:
                f.seek(max(0, tamanho - limite))
                dados = f.read()
        except OSError:
            return ""
        return _decodificar(dados).replace("\r\n", "\n").strip()

    def estado(self) -> str:
        return "rodando" if self.vivo() else f"terminou (código {self.codigo})"

    def linha(self) -> str:
        seg = int(time.monotonic() - self.inicio)
        tempo = f"{seg // 60} min" if seg >= 60 else f"{seg} s"
        primeira = (self.comando.splitlines() or [""])[0][:80]
        return f"{self.id} · {self.estado()} · pid {self.pid} · há {tempo} · $ {primeira}"

    def _limpar_script(self):
        if self.script is not None and not self.vivo():
            try:
                self.script.unlink()
            except OSError:
                pass
            self.script = None


class Gerenciador:
    """Guarda os processos em segundo plano da sessão do app."""

    def __init__(self, pasta_logs):
        self.pasta = Path(pasta_logs)
        self._itens: dict[int, Processo] = {}
        self._ids = itertools.count(1)
        self._trava = threading.Lock()

    # ---------------- ciclo de vida ----------------

    def iniciar(self, comando: str, cwd) -> Processo:
        texto = (comando or "").strip()
        if not texto:
            raise ComandoRecusado("Comando vazio.")
        pasta = Path(cwd).expanduser()
        if not pasta.is_dir():
            raise ComandoRecusado(f"Pasta de trabalho não existe: {pasta}")
        self.pasta.mkdir(parents=True, exist_ok=True)
        with self._trava:
            numero = next(self._ids)
        log = self.pasta / f"processo-{time.strftime('%Y%m%d-%H%M%S')}-{numero}.log"
        args, usa_shell, script = _preparar(texto)
        # Saída em arquivo, como no runner: processo filho que fica no fundo
        # herda o handle, e pipe só fecharia quando ele morresse.
        with open(log, "wb") as saida:
            proc = subprocess.Popen(
                args, cwd=str(pasta), shell=usa_shell,
                stdin=subprocess.DEVNULL, stdout=saida, stderr=subprocess.STDOUT,
                creationflags=_SEM_JANELA,
                env={**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"})
        processo = Processo(numero, texto, str(pasta), proc, log, script)
        with self._trava:
            self._itens[numero] = processo
        return processo

    def esperar_pronto(self, processo: Processo,
                       max_seg: float = ESPERA_MAXIMA_PADRAO,
                       silencio_seg: float = SILENCIO_PRONTO_PADRAO,
                       ao_progredir=None, cancelado=None) -> tuple[str, int]:
        """Bloqueia até o comando terminar ou parecer pronto → (motivo, posição lida).

        motivo: `terminou` (não era contínuo), `pronto` (sinal de servidor no
        ar), `silencio` (falou e ficou quieto por `silencio_seg`), `limite`
        (passou `max_seg`) ou `cancelado`. Rodar numa thread: não toca Qt.
        """
        inicio = time.monotonic()
        pos = 0
        ultima_saida = None
        recente = ""
        decodificador = codecs.getincrementaldecoder("utf-8")("replace")

        def ler():
            nonlocal pos, ultima_saida, recente
            dados, pos = processo.ler_bytes(pos)
            if dados:
                texto = decodificador.decode(dados)
                recente = (recente + texto)[-4000:]
                ultima_saida = time.monotonic()
                if ao_progredir is not None:
                    try:
                        ao_progredir(texto)
                    except Exception:
                        pass
            return bool(dados)

        while True:
            ler()
            if not processo.vivo():
                time.sleep(0.1)
                ler()
                processo._limpar_script()
                return "terminou", pos
            if _PRONTO_RE.search(recente):
                time.sleep(0.5)
                ler()
                return "pronto", pos
            if cancelado is not None and cancelado():
                return "cancelado", pos
            agora = time.monotonic()
            if ultima_saida is not None and agora - ultima_saida >= silencio_seg:
                return "silencio", pos
            if agora - inicio >= max_seg:
                return "limite", pos
            time.sleep(0.2)

    def parar(self, numero: int, espera: float = 5.0) -> bool:
        processo = self.obter(numero)
        if processo is None:
            return False
        if processo.vivo():
            encerrar(processo.proc)
            try:
                processo.proc.wait(timeout=espera)
            except subprocess.TimeoutExpired:
                pass
        processo._limpar_script()
        return not processo.vivo()

    def parar_todos(self):
        for processo in self.listar():
            if processo.vivo():
                self.parar(processo.id)

    # ---------------- consulta ----------------

    def obter(self, numero) -> Processo | None:
        with self._trava:
            return self._itens.get(numero)

    def listar(self) -> list[Processo]:
        with self._trava:
            return list(self._itens.values())

    def vivos(self) -> list[Processo]:
        return [p for p in self.listar() if p.vivo()]

    # ---------------- comandos internos (@processos, @saida, @parar) ----------------

    def executar_interno(self, nome: str, numero: int | None) -> str:
        if nome == "processos":
            itens = self.listar()
            if not itens:
                return "$ @processos\n(nenhum processo em segundo plano nesta sessão)"
            return "$ @processos\n" + "\n".join(p.linha() for p in itens)
        if numero is None:
            return f"$ @{nome}\n(informe o número do processo, por exemplo @{nome} 1)"
        processo = self.obter(numero)
        if processo is None:
            return f"$ @{nome} {numero}\n(processo {numero} não existe; veja @processos)"
        if nome == "saida":
            return (f"$ @saida {numero}\n({processo.estado()}; últimas linhas do log)\n"
                    + (processo.cauda() or "(sem saída ainda)"))
        parou = self.parar(numero)
        return (f"$ @parar {numero}\n"
                + ("(processo encerrado)" if parou else "(não consegui encerrar; tente de novo)"))
