"""Gera o manifest.json que o updater consulta a cada release.

Uso:
    python instalador/gerar_manifesto.py [--versao 1.1.0]
                                        [--notas "texto"]
                                        [--min-versao 1.0.0]
                                        [--url-base URL]

Lê:
    - src/__version__.py (versão atual)
    - dist/instalador/DeepSeekUI-Setup-<versao>.exe (gerado por build.bat)
    - instalador/notas/v<versao>.md (opcional, notas do release)

Escreve:
    dist/instalador/manifest.json

Nada é enviado ao GitHub. O script só prepara arquivos e imprime o
`gh release create` para o usuário rodar manualmente.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
URL_BASE_PADRAO = (
    "https://github.com/SEU_USUARIO/deepseek-ui/releases/download/v{versao}"
)


def sha256_arquivo(caminho: Path) -> str:
    h = hashlib.sha256()
    with caminho.open("rb") as f:
        for bloco in iter(lambda: f.read(1024 * 1024), b""):
            h.update(bloco)
    return h.hexdigest()


def ler_versao() -> str:
    arquivo = RAIZ / "src" / "__version__.py"
    texto = arquivo.read_text(encoding="utf-8")
    m = re.search(r'__version__\s*=\s*[\'"]([^\'"]+)[\'"]', texto)
    if not m:
        raise SystemExit("não consegui ler __version__ em src/__version__.py")
    return m.group(1)


def ler_notas(versao: str) -> str:
    candidatos = [
        RAIZ / "instalador" / "notas" / f"v{versao}.md",
        RAIZ / "instalador" / "RELEASE_NOTES.md",
    ]
    for c in candidatos:
        if c.is_file():
            return c.read_text(encoding="utf-8").strip()
    return ""


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--versao", help="sobrescreve src/__version__.py")
    p.add_argument("--notas", help="texto inline (sobrescreve arquivo de notas)")
    p.add_argument("--min-versao", default="",
                   help="min_versao_compat do manifesto (default: vazio)")
    p.add_argument("--url-base", default=None,
                   help="URL base do release; default: github.com/SEU_USUARIO/...")
    args = p.parse_args()

    versao = args.versao or ler_versao()
    exe = RAIZ / "dist" / "instalador" / f"DeepSeekUI-Setup-{versao}.exe"
    if not exe.is_file():
        print(f"não achei {exe}", file=sys.stderr)
        print("rode build.bat antes de gerar o manifesto", file=sys.stderr)
        return 1

    url_base = (args.url_base or URL_BASE_PADRAO).format(versao=versao)
    sha = sha256_arquivo(exe)
    notas = args.notas if args.notas is not None else ler_notas(versao)

    manifesto = {
        "versao": versao,
        "url": f"{url_base.rstrip('/')}/{exe.name}",
        "sha256": sha,
        "notas": notas,
        "min_versao_compat": args.min_versao,
    }
    destino = exe.parent / "manifest.json"
    destino.write_text(
        json.dumps(manifesto, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8")

    print(f"manifesto: {destino}")
    print(f"versao:    {versao}")
    print(f"sha256:    {sha}")
    print(f"tamanho:   {exe.stat().st_size} bytes")
    if "SEU_USUARIO" in url_base:
        print()
        print("AVISO: URL ainda tem SEU_USUARIO. Use --url-base ou edite o manifesto.")

    notas_existente = RAIZ / "instalador" / "notas" / f"v{versao}.md"
    notas_arg = (f'--notes-file "{notas_existente}"'
                 if notas_existente.is_file() else '--notes ""')
    print()
    print("Nada foi enviado. Proximo passo (manual, decida voce):")
    print(f'  gh release create v{versao} --title "v{versao}" {notas_arg} \\')
    print(f'      "{exe}" "{destino}"')
    print()
    print("Antes disso, garanta que:")
    print("  - o repositorio novo ja existe no GitHub")
    print("  - a URL base no manifesto aponta para esse repositorio")
    return 0


if __name__ == "__main__":
    sys.exit(main())
