"""Roda os comandos que o agente pede — sem travas de conteúdo.

Liberado a pedido do usuário em 2026-10-19 ([[ADR-022 Shell livre para o
agente]], que substitui a allowlist do ADR-006): qualquer programa e
argumento, pipes, redirecionamento, `;`, `&&`, `||`, `cd` para qualquer
pasta e várias linhas. O comando roda no shell do sistema (`cmd.exe` no
Windows), começando na raiz do projeto. Várias linhas viram um script `.cmd`
temporário, então `cd` e variáveis valem de uma linha para a outra.

O que continua, e por quê:

- **Confirmação** é do perfil de Acesso, decidida antes de chegar aqui:
  perfis com confirmação mostram o comando; os automáticos rodam direto.
- **`timeout` padrão de 5 min**, com `ao_progredir` chamado a cada ~250 ms —
  o chamador vê a saída ao vivo e recebe `Saida.motivo="timeout"` sem
  esperar mais que isso. O botão Parar (`encerrar`) continua derrubando a
  árvore de processos a qualquer momento. `stdin` fechado: comando que
  espera teclado recebe fim de entrada em vez de ficar esperando para sempre.
- **`limite_sem_saida`** (padrão 120 s): aviso, **não fatal**. Quando um
  comando fica sem produzir saída por esse tempo, `ao_progredir("", seg)`
  é chamado uma vez para o chamador sinalizar no cabeçalho. Servidor que
  ficou pendurado é distinguido de build silencioso sem matar ninguém — a
  decisão de parar é do usuário.
- `destrutivo()` só pinta o aviso ⚠ no diálogo de confirmação.

Não há desfazer para comando: arquivo apagado por ele não passa pelo backup.
"""

import codecs
import ctypes
import locale
import os
import shlex
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

# Comandos longos (build, instalação) rodam até o fim; o default evita que
# um servidor esquecido prenda a UI para sempre. O `Parar` (encerrar) continua
# disponível em qualquer momento, e comandos realmente longos podem passar
# `timeout=None` explicitamente.
TIMEOUT_PADRAO: float | None = 300.0

# Tempo sem saída até o chamador receber o aviso de silêncio (não fatal).
LIMITE_SEM_SAIDA_PADRAO: float | None = 120.0

_SEM_JANELA = getattr(subprocess, "CREATE_NO_WINDOW", 0)

# Só para o aviso ⚠ no diálogo de confirmação — não bloqueia nada.
MARCAS_DESTRUTIVAS = {
    "rm", "del", "erase", "rmdir", "rd", "format", "remove-item", "shutdown",
    "taskkill", "reg", "diskpart", "mkfs", "dd",
    "--force", "-f", "-rf", "-fr", "/s", "/q", "--hard",
    "push", "reset", "clean", "rebase",
    "install", "uninstall", "publish", "deploy", "migrate", "upgrade", "drop",
}


class ComandoRecusado(Exception):
    """Comando vazio ou pasta de trabalho inexistente."""


@dataclass
class Saida:
    comando: str
    codigo: int
    texto: str
    estourou_tempo: bool = False
    interrompido: bool = False
    # ok | timeout | interrompido | erro
    #   ok: processo terminou (com qualquer código de saída)
    #   timeout: encerrado por estourar `timeout`
    #   interrompido: encerrado pelo botão Parar
    #   erro: falha do próprio app antes/durante o Popen (Popen falhou,
    #   comando recusado, etc.) — não houve processo do comando.
    motivo: str = "ok"
    segundos: float = 0.0

    @property
    def ok(self) -> bool:
        return (self.codigo == 0 and not self.estourou_tempo
                and not self.interrompido and self.motivo == "ok")

    def resumo(self) -> str:
        if self.interrompido:
            return f"$ {self.comando}\n(interrompido por você)\n{self.texto}"
        if self.estourou_tempo:
            return (f"$ {self.comando}\n(tempo esgotado após "
                    f"{self.segundos:.0f}s)\n{self.texto}")
        if self.motivo == "erro":
            return f"$ {self.comando}\n(erro)\n{self.texto}"
        return f"$ {self.comando}\n(saiu com {self.codigo})\n{self.texto}"


def destrutivo(comando: str) -> bool:
    """Merece o aviso ⚠ na confirmação. Não impede a execução."""
    try:
        tokens = shlex.split(comando or "", posix=False)
    except ValueError:
        return True  # não deu para ler: trate como perigoso
    vistos = {t.strip("\"'").lower() for t in tokens}
    vistos |= {os.path.basename(t).lower().removesuffix(".exe") for t in vistos}
    return bool(vistos & MARCAS_DESTRUTIVAS)


def _codepage_console() -> str | None:
    if os.name != "nt":
        return None
    try:
        return f"cp{ctypes.windll.kernel32.GetOEMCP()}"
    except Exception:
        return None


def _decodificar(dados: bytes | None) -> str:
    """UTF-8 primeiro; senão a página de código do console (cmd fala cp850)."""
    if not dados:
        return ""
    for codificacao in ("utf-8", _codepage_console(),
                        locale.getpreferredencoding(False), "cp1252"):
        if not codificacao:
            continue
        try:
            return dados.decode(codificacao)
        except (UnicodeDecodeError, LookupError):
            continue
    return dados.decode("utf-8", errors="replace")


def _preparar(texto: str):
    """Devolve (args, usa_shell, script_temporário)."""
    if "\n" not in texto:
        return texto, True, None
    if os.name != "nt":
        return texto, True, None  # `sh -c` aceita várias linhas
    fd, nome = tempfile.mkstemp(prefix="deepseek_ui_", suffix=".cmd")
    with os.fdopen(fd, "w", encoding="utf-8", newline="\r\n") as arquivo:
        arquivo.write("@echo off\nchcp 65001 >nul\n" + texto + "\n")
    comspec = os.environ.get("COMSPEC", "cmd.exe")
    return [comspec, "/d", "/c", nome], False, Path(nome)


def encerrar(proc) -> None:
    """Derruba o comando e tudo o que ele abriu (o Parar usa isto)."""
    if proc is None or proc.poll() is not None:
        return
    proc.deepseek_interrompido = True
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)],
                           capture_output=True, creationflags=_SEM_JANELA)
        else:
            proc.kill()
    except OSError:
        proc.kill()


def rodar(comando: str, cwd,
          timeout: float | None = TIMEOUT_PADRAO,
          limite_sem_saida: float | None = LIMITE_SEM_SAIDA_PADRAO,
          ao_iniciar=None, ao_progredir=None) -> Saida:
    """Executa `comando` no shell do sistema, a partir de `cwd`.

    `ao_iniciar(proc)` recebe o processo assim que ele sobe — é por onde a
    interface guarda a referência para o botão Parar.

    `ao_progredir(texto_novo: str, seg_sem_saida: float)` é chamado enquanto
    o processo vive, com os bytes novos desde a última chamada e o tempo (s)
    desde a última saída. Chamado da thread do comando; o chamador deve
    encaminhar para a GUI por sinal se precisar. Quando o processo cruza
    `limite_sem_saida` sem produzir saída, é chamado uma vez com `texto_novo`
    vazio e `seg_sem_saida` >= esse limite — o chamador decide se avisa ou
    se encerra.
    """
    texto = (comando or "").strip()
    if not texto:
        raise ComandoRecusado("Comando vazio.")
    pasta = Path(cwd).expanduser()
    if not pasta.is_dir():
        raise ComandoRecusado(f"Pasta de trabalho não existe: {pasta}")

    args, usa_shell, script = _preparar(texto)
    # Saída num arquivo temporário, não num pipe: processo que o comando deixa
    # em segundo plano (servidor do `adb`, `start /b`…) herda o handle de saída.
    # Com pipe, o fim da leitura só vinha quando ESSE processo morria — o app
    # ficou 40 min parado num `adb devices` (2026-10-20). Com arquivo, o fim é
    # o fim do processo do comando, e o arquivo some quando o último handle fecha.
    saida = tempfile.TemporaryFile()
    inicio = time.monotonic()
    estourou = False
    silencioso = False
    pos = 0
    buffer_bruto = b""
    ultima_saida = inicio
    decodificador = codecs.getincrementaldecoder("utf-8")("replace")

    try:
        try:
            proc = subprocess.Popen(
                args,
                cwd=str(pasta),
                shell=usa_shell,
                stdin=subprocess.DEVNULL,
                stdout=saida,
                stderr=subprocess.STDOUT,
                creationflags=_SEM_JANELA,
                # Python no pipe fala cp1252; em UTF-8 a saída volta legível.
                env={**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"},
            )
        except OSError as e:
            return Saida(texto, -1, f"Falhou ao executar: {e}", motivo="erro")
        if ao_iniciar is not None:
            try:
                ao_iniciar(proc)
            except Exception:
                pass

        # Loop de watchdog + streaming. `proc.wait(timeout=0.25)` retorna
        # imediatamente quando o processo termina; se ele continua vivo,
        # lemos o que chegou novo no arquivo de saída e avisamos silêncio.
        while True:
            if timeout is not None and (time.monotonic() - inicio) >= timeout:
                estourou = True
                encerrar(proc)
                proc.deepseek_interrompido = False
                proc.wait()
                break
            try:
                proc.wait(timeout=0.25)
                break
            except subprocess.TimeoutExpired:
                pass

            saida.seek(pos)
            novos = saida.read()
            if novos:
                pos = saida.tell()
                buffer_bruto += novos
                ultima_saida = time.monotonic()
                silencioso = False
                if ao_progredir is not None:
                    try:
                        ao_progredir(decodificador.decode(novos), 0.0)
                    except Exception:
                        pass

            if (ao_progredir is not None
                    and limite_sem_saida is not None
                    and not silencioso
                    and proc.poll() is None
                    and (time.monotonic() - ultima_saida) >= limite_sem_saida):
                silencioso = True
                try:
                    ao_progredir("", time.monotonic() - ultima_saida)
                except Exception:
                    pass

        # Última leitura: garante que a saída final não se perdeu.
        saida.seek(pos)
        restante = saida.read()
        if restante:
            buffer_bruto += restante
            if ao_progredir is not None:
                try:
                    ao_progredir(decodificador.decode(restante), 0.0)
                except Exception:
                    pass

        segundos = time.monotonic() - inicio
        interrompido = bool(getattr(proc, "deepseek_interrompido", False))
        if estourou:
            motivo = "timeout"
            codigo = -1
        elif interrompido:
            motivo = "interrompido"
            codigo = -1
        else:
            motivo = "ok"
            codigo = proc.returncode
        return Saida(
            texto, codigo,
            _decodificar(buffer_bruto).replace("\r\n", "\n").strip(),
            estourou_tempo=estourou, interrompido=interrompido,
            motivo=motivo, segundos=segundos)
    finally:
        saida.close()
        if script is not None:
            try:
                script.unlink()
            except OSError:
                pass
