"""O que fazer com o que você cola no chat.

Duas formas de anexar, porque servem a coisas diferentes:

  • **inline** — o conteúdo do arquivo vai como texto no rodapé do pedido, com o
    caminho marcado. É o que serve para código: o modelo vê o caminho e pode
    devolver uma alteração para ele.
  • **upload** — o arquivo sobe de verdade pelo `<input type=file>` do DeepSeek.
    É o único jeito de mandar imagem: ela não cabe no texto.

A escolha é automática: texto que dá para ler vira inline, o resto vira upload.
Imagem colada da área de transferência não é arquivo ainda, então vira PNG numa
pasta temporária antes de subir.
"""

import os
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

# Acima disso, colar o conteúdo no prompt gasta contexto demais — vai como upload.
MAX_INLINE_BYTES = 100_000

EXT_TEXTO = {
    ".py", ".js", ".jsx", ".ts", ".tsx", ".html", ".htm", ".css", ".scss",
    ".json", ".yaml", ".yml", ".xml", ".md", ".txt", ".ini", ".cfg", ".toml",
    ".sh", ".bat", ".ps1", ".sql", ".java", ".c", ".h", ".cpp", ".hpp", ".cs",
    ".go", ".rs", ".rb", ".php", ".lua", ".vue", ".svelte", ".env", ".gitignore",
    ".kt", ".swift", ".dart", ".r", ".pl", ".ex", ".exs", ".scala", ".clj",
}


def _pasta_temp() -> Path:
    pasta = Path(tempfile.gettempdir()) / "deepseek_ui_anexos"
    pasta.mkdir(parents=True, exist_ok=True)
    return pasta


@dataclass
class Anexo:
    """Uma coisa pendurada no próximo pedido."""

    rotulo: str                 # o que aparece no chip
    modo: str                   # 'inline' | 'upload'
    caminho: str | None = None  # para upload
    conteudo: str | None = None # para inline
    temporario: bool = False    # foi criado por nós (imagem colada)

    @property
    def icone(self) -> str:
        return "🖼" if self.modo == "upload" else "📄"

    def descartar(self):
        """Apaga o temporário que nós criamos. Arquivo do usuário não se toca."""
        if self.temporario and self.caminho:
            try:
                os.unlink(self.caminho)
            except OSError:
                pass


def _e_texto(caminho: Path) -> bool:
    if caminho.suffix.lower() in EXT_TEXTO:
        return True
    if caminho.suffix:
        return False
    # Sem extensão (Makefile, Dockerfile): decide pelo conteúdo.
    try:
        amostra = caminho.open("rb").read(2048)
    except OSError:
        return False
    if b"\x00" in amostra:
        return False
    try:
        amostra.decode("utf-8")
        return True
    except UnicodeDecodeError:
        return False


def de_arquivo(caminho, raiz=None) -> Anexo | None:
    """Um arquivo do disco vira anexo. `raiz` só encurta o rótulo."""
    p = Path(caminho)
    if not p.is_file():
        return None

    rotulo = p.name
    if raiz:
        try:
            rotulo = p.resolve().relative_to(Path(raiz).resolve()).as_posix()
        except (ValueError, OSError):
            pass

    try:
        tamanho = p.stat().st_size
    except OSError:
        return None

    if _e_texto(p) and tamanho <= MAX_INLINE_BYTES:
        try:
            return Anexo(rotulo, "inline",
                         conteudo=p.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            return None

    return Anexo(rotulo, "upload", caminho=str(p.resolve()))


def de_imagem(imagem) -> Anexo | None:
    """QImage da área de transferência → PNG temporário pronto para subir."""
    if imagem is None or imagem.isNull():
        return None
    nome = f"colado-{time.strftime('%Y%m%d-%H%M%S')}-{int(time.time() * 1000) % 1000}.png"
    destino = _pasta_temp() / nome
    if not imagem.save(str(destino), "PNG"):
        return None
    lado = f"{imagem.width()}×{imagem.height()}"
    return Anexo(f"imagem colada ({lado})", "upload",
                 caminho=str(destino), temporario=True)


def separar(anexos: list[Anexo]):
    """Divide em (inline para o prompt, caminhos para upload)."""
    inline = [(a.rotulo, a.conteudo or "") for a in anexos if a.modo == "inline"]
    upload = [a.caminho for a in anexos if a.modo == "upload" and a.caminho]
    return inline, upload
