"""Testes de tela com o runtime Playwright do computador ([[ADR-026 Testes de tela pelo runtime Playwright]]).

O app não guarda caminho fixo nem nada de projeto específico: procura
`<Documentos>\\Playwright-Lab\\runtime.cjs` (ou a pasta em
`DEEPSEEK_UI_PLAYWRIGHT`) e, se existir, ensina o agente o padrão do usuário —
headless primeiro, mapear antes de clicar, passo a passo com um print por etapa
e headed só para demonstrar. Sem runtime, mas com o instalador do hub de
memória, o agente sabe como criar. Sem nenhum dos dois, não injeta nada.
"""

import ctypes
import os
from pathlib import Path

_CSIDL_PERSONAL = 5  # pasta Documentos do usuário atual
_DETECTAR = object()


def pasta_documentos() -> Path:
    """Documentos do usuário atual, mesmo quando redirecionada (OneDrive)."""
    if os.name == "nt":
        try:
            buffer = ctypes.create_unicode_buffer(32768)
            if (ctypes.windll.shell32.SHGetFolderPathW(None, _CSIDL_PERSONAL, None, 0, buffer) == 0
                    and buffer.value):
                return Path(buffer.value)
        except Exception:
            pass
    return Path.home() / "Documents"


def runtime_playwright() -> Path | None:
    """Pasta do runtime (com `runtime.cjs`), ou None se não houver."""
    override = os.environ.get("DEEPSEEK_UI_PLAYWRIGHT")
    base = Path(override) if override else pasta_documentos() / "Playwright-Lab"
    return base if (base / "runtime.cjs").is_file() else None


def instalador_playwright() -> Path | None:
    caminho = (pasta_documentos() / "AI_Memory_Vault" / "90_SYSTEM"
               / "playwright-runtime" / "instalar.ps1")
    return caminho if caminho.is_file() else None


def regras(runtime=_DETECTAR, instalador=_DETECTAR) -> str:
    """Bloco do prompt sobre testes de tela; vazio se não houver runtime nem instalador."""
    if runtime is _DETECTAR:
        runtime = runtime_playwright()
    if instalador is _DETECTAR:
        instalador = instalador_playwright()
    if runtime is None:
        if instalador is None:
            return ""
        return ("TESTES DE TELA:\n\n"
                "- Este computador ainda não tem o runtime Playwright. Se o usuário pedir "
                "teste ou validação em tela, proponha criar com o comando "
                f'`powershell -NoProfile -ExecutionPolicy Bypass -File "{Path(instalador).as_posix()}"` '
                "(precisa de Node.js) e siga o padrão: headless primeiro, mapear antes de "
                "clicar, passo a passo com um print por etapa.")
    rt = Path(runtime).as_posix()
    return f"""\
TESTES DE TELA (runtime Playwright deste computador em `{rt}`):

- Para testar, validar ou documentar um fluxo em tela (site, app web, formulário,
  HTML local), use esse runtime pelos comandos do app. Não instale outro
  Playwright nem Chromium.
- Headless sempre para descobrir onde clicar e para validar. Primeiro mapeie:
  `node "{rt}/mapear.cjs" "<url ou arquivo.html>" "evidencias/mapa"` gera
  pagina.png e mapa.json com campos, botões, links e seletor sugerido. Escreva o
  fluxo a partir do mapa, não por tentativa.
- Rode o fluxo num script do projeto (por exemplo `evidencias/fluxo.cjs`) com
  `const {{ abrir, passoAPasso }} = require("{rt}/runtime.cjs")`; `abrir()` é
  headless.
- Passo a passo (step-by-step): `const pp = passoAPasso(page, "evidencias/<fluxo>",
  "<título>")`, `await pp.passo("ação", {{ esperado, observado, status }})` a cada
  etapa e `pp.concluir("PASSOU")` ou `pp.concluir("FALHOU")`, que grava
  passo-a-passo.md e passos.json com um print numerado por passo.
- Headed (janela visível) só para demonstrar um fluxo já mapeado ou quando o
  usuário pedir: `abrir({{ headed: true }})`.
- Servidor de desenvolvimento sobe em segundo plano pelo app; use o endereço que
  aparecer na saída. Só dados fictícios. Não declare teste passado sem rodar e sem
  conferir os prints."""
