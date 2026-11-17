"""Sandbox: decide se um caminho vindo do modelo pode ser tocado.

Regra única: o caminho final, depois de resolvido, tem que estar DENTRO da raiz
autorizada. Tudo aqui existe para que essa regra não possa ser furada — o modelo
escreve o caminho, e um caminho é a coisa mais fácil de disfarçar que existe.

Nada neste módulo escreve em disco. Só valida e devolve o caminho absoluto.
"""

import os
from pathlib import Path, PurePath

# Nomes que o Windows reserva para dispositivos: um arquivo "CON.txt" não é um
# arquivo, é o console. Abrir para escrita trava ou escreve no lugar errado.
_RESERVED = (
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{i}" for i in range(1, 10)}
    | {f"LPT{i}" for i in range(1, 10)}
)

# Teto por arquivo. Resposta de chat não produz arquivo de 2 MB; se produziu,
# alguma coisa está errada e é melhor recusar do que gravar.
MAX_BYTES = 2_000_000


class SandboxError(Exception):
    """Caminho recusado. A mensagem é mostrada ao usuário."""


def _same_or_inside(path: Path, root: Path) -> bool:
    """`path` está dentro de `root`?

    Compara os dois já resolvidos e com `normcase` aplicado, porque o NTFS não
    diferencia maiúscula de minúscula e `relative_to` compara texto. Sem isso,
    C:\\Users\\X e C:\\users\\x seriam "pastas diferentes".
    """
    try:
        Path(os.path.normcase(str(path))).relative_to(Path(os.path.normcase(str(root))))
        return True
    except ValueError:
        return False


class Sandbox:
    """Raiz autorizada. Só caminhos relativos a ela passam."""

    def __init__(self, root, max_bytes: int = MAX_BYTES):
        raiz = Path(root).expanduser()
        try:
            self.root = raiz.resolve(strict=True)
        except OSError as e:
            raise SandboxError(f"Pasta não encontrada: {root} ({e})") from e
        if not self.root.is_dir():
            raise SandboxError(f"Não é uma pasta: {self.root}")
        self.max_bytes = max_bytes

    def __repr__(self):
        return f"Sandbox({self.root})"

    # ---------------- validação ----------------

    def resolve(self, rel: str) -> Path:
        """Valida `rel` e devolve o caminho absoluto dentro da raiz.

        Levanta `SandboxError` com o motivo em qualquer suspeita. Não checa se o
        arquivo existe — isso é decisão de quem chama.
        """
        if not isinstance(rel, str):
            raise SandboxError("Caminho vazio.")
        if "\x00" in rel:
            raise SandboxError("Caminho com byte nulo.")

        # Tira só quebra de linha e tab (ruído do parser). Espaço NÃO: um nome
        # como "arq " tem que ser recusado, não corrigido em silêncio — o
        # Windows apaga o espaço do fim sozinho e gravaria em "arq", diferente
        # do que foi revisado no diff.
        bruto = rel.strip("\n\r\t")
        if not bruto.strip():
            raise SandboxError("Caminho vazio.")

        limpo = bruto.replace("\\", "/")

        # Caminho absoluto, unidade (C:...) ou UNC (//servidor/share): o modelo
        # não escolhe onde a raiz fica, só o que fica dentro dela.
        drive, resto = os.path.splitdrive(limpo)
        if drive:
            raise SandboxError(f"Caminho com unidade ou de rede não é aceito: {rel}")
        if PurePath(limpo).is_absolute() or limpo.startswith("/"):
            raise SandboxError(f"Caminho absoluto não é aceito, use relativo: {rel}")
        if ":" in resto:
            # Alternate Data Stream do NTFS: "nota.txt:oculto" grava num fluxo
            # invisível do arquivo, que passaria batido em qualquer revisão.
            raise SandboxError(f"Caminho com ':' não é aceito: {rel}")

        partes = [p for p in limpo.split("/") if p not in ("", ".")]
        if not partes:
            raise SandboxError(f"Caminho sem nome de arquivo: {rel}")

        for parte in partes:
            if parte == "..":
                raise SandboxError(f"'..' não é aceito no caminho: {rel}")
            if parte != parte.strip() or parte != parte.rstrip("."):
                # O Windows corta espaço/ponto do fim em silêncio: o que a gente
                # valida ("a .txt ") não é o que ele abre ("a .txt").
                raise SandboxError(f"Nome com espaço ou ponto sobrando: {parte!r}")
            if parte.split(".")[0].upper() in _RESERVED:
                raise SandboxError(f"Nome reservado do Windows: {parte}")

        candidato = self.root.joinpath(*partes)

        # Symlink/junction em QUALQUER componente, não só no destino: uma pasta
        # "src" que aponte para fora levaria "src/app.py" para fora junto.
        atual = self.root
        for parte in partes:
            atual = atual / parte
            if atual.is_symlink() or (hasattr(atual, "is_junction") and atual.is_junction()):
                raise SandboxError(f"Componente é link e sai da raiz: {parte}")

        final = candidato.resolve()
        if not _same_or_inside(final, self.root):
            raise SandboxError(f"Caminho sai da pasta autorizada: {rel}")
        if final == self.root:
            raise SandboxError("Não dá para escrever sobre a própria raiz.")
        return final

    def relative(self, path) -> str:
        """Caminho bonito para mostrar na UI (sempre com '/')."""
        try:
            return Path(path).relative_to(self.root).as_posix()
        except ValueError:
            return str(path)

    def check_size(self, conteudo: str, rel: str = ""):
        tamanho = len(conteudo.encode("utf-8"))
        if tamanho > self.max_bytes:
            raise SandboxError(
                f"Arquivo grande demais ({tamanho} bytes, teto {self.max_bytes}): {rel}")
