"""Cópia de segurança antes de qualquer escrita.

O modelo manda o arquivo INTEIRO em toda modificação. Se ele truncar a resposta,
o que chega é um arquivo pela metade — e gravar isso por cima apaga o original.
Aqui todo arquivo tocado vira cópia antes, e apagar é mover para cá, nunca
`unlink`. Assim nada do que o modelo faz é irreversível.

Fica em `.deepseek_ui/backups/<AAAAMMDD-HHMMSS>/<caminho relativo>`.
"""

import shutil
import time
from pathlib import Path

PASTA = ".deepseek_ui"


class Backup:
    def __init__(self, root):
        self.root = Path(root)
        self.dir = self.root / PASTA / "backups"
        self._lote = None

    def novo_lote(self) -> str:
        """Abre um lote — uma aplicação de resposta inteira cai na mesma pasta."""
        base = time.strftime("%Y%m%d-%H%M%S")
        lote, n = base, 2
        while (self.dir / lote).exists():
            lote = f"{base}-{n}"
            n += 1
        self._lote = lote
        return lote

    def _destino(self, rel: str) -> Path:
        if self._lote is None:
            self.novo_lote()
        destino = self.dir / self._lote / rel
        destino.parent.mkdir(parents=True, exist_ok=True)
        return destino

    def salvar(self, caminho: Path, rel: str) -> Path | None:
        """Copia o arquivo atual para o lote. Devolve onde ficou, ou None se não existia."""
        caminho = Path(caminho)
        if not caminho.is_file():
            return None
        destino = self._destino(rel)
        shutil.copy2(caminho, destino)
        return destino

    def mover(self, caminho: Path, rel: str) -> Path | None:
        """Apagar = mover para o lote. Devolve onde ficou, ou None se não existia."""
        caminho = Path(caminho)
        if not caminho.exists():
            return None
        destino = self._destino(rel)
        shutil.move(str(caminho), str(destino))
        return destino

    def caminho_do_lote(self) -> Path | None:
        return (self.dir / self._lote) if self._lote else None
