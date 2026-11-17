"""Permissões por projeto e resolução segura de caminhos autorizados."""

import os
from pathlib import Path, PureWindowsPath
from typing import TypedDict

from src.sandbox import Sandbox, SandboxError

MODOS = {
    "project_confirm", "project_auto", "folders",
    "computer_confirm", "computer_auto",
}
OPERACOES = {"ler", "criar", "modificar", "apagar"}
_CHAVES_OPERACAO = {
    "ler": "read",
    "criar": "create",
    "modificar": "edit",
    "apagar": "delete",
}


class FolderGrant(TypedDict):
    path: str
    read: bool
    create: bool
    edit: bool
    delete: bool


def _dentro(caminho: Path, raiz: Path) -> bool:
    try:
        Path(os.path.normcase(str(caminho))).relative_to(
            Path(os.path.normcase(str(raiz))))
        return True
    except ValueError:
        return False


def _bloqueados_windows() -> list[Path]:
    unidade = os.environ.get("SystemDrive", "C:")
    raiz_windows = os.environ.get("WINDIR") or os.environ.get("SystemRoot")
    caminhos = [
        Path(raiz_windows) if raiz_windows else Path(unidade) / "Windows",
        Path(os.environ.get("ProgramFiles", str(Path(unidade) / "Program Files"))),
        Path(os.environ.get("ProgramFiles(x86)",
                           str(Path(unidade) / "Program Files (x86)"))),
        Path(os.environ.get("ProgramData", str(Path(unidade) / "ProgramData"))),
        Path(unidade) / "$Recycle.Bin",
        Path(unidade) / "System Volume Information",
        Path(unidade) / "Recovery",
        Path(unidade) / "Config.Msi",
        Path(unidade) / "PerfLogs",
    ]
    return [p.resolve(strict=False) for p in caminhos]


class PermissionPolicy:
    """Autoriza operações no projeto, em pastas concedidas ou no computador.

    A política não executa comandos. Mesmo no modo automático, comandos passam
    pelo runner do app e suas restrições próprias.
    """

    def __init__(self, project_root, mode="project_confirm", grants=None,
                 confirm_reads=True):
        self.project = Sandbox(project_root)
        if mode not in MODOS:
            raise ValueError(f"Modo de permissão desconhecido: {mode}")
        if not isinstance(confirm_reads, bool):
            raise ValueError("A confirmação de leitura precisa ser booleana.")
        self.mode = mode
        self.confirm_reads = confirm_reads
        self._bloqueados = _bloqueados_windows()
        self._unidade_sistema = (os.environ.get("SystemDrive") or "C:").rstrip("\\/")
        self.grants = self._validar_grants([] if grants is None else grants)
        self._checar_bloqueado(self.project.root)
        for grant in self.grants:
            self._checar_bloqueado(Path(grant["path"]))

    @staticmethod
    def _validar_grants(grants) -> list[FolderGrant]:
        if not isinstance(grants, list):
            raise ValueError("A lista de permissões por pasta é inválida.")
        normalizados = []
        vistos = set()
        for grant in grants:
            if not isinstance(grant, dict) or not isinstance(grant.get("path"), str):
                raise ValueError("Permissão de pasta sem caminho válido.")
            raiz = Path(grant["path"]).expanduser()
            if not raiz.is_absolute() or not raiz.is_dir():
                raise ValueError(f"Pasta autorizada não encontrada: {raiz}")
            if raiz.is_symlink() or (hasattr(raiz, "is_junction") and raiz.is_junction()):
                raise ValueError(f"Pasta autorizada é um link: {raiz}")
            raiz = raiz.resolve(strict=True)
            regra: FolderGrant = {
                "path": str(raiz), "read": False, "create": False,
                "edit": False, "delete": False,
            }
            for chave in ("read", "create", "edit", "delete"):
                valor = grant.get(chave, False)
                if not isinstance(valor, bool):
                    raise ValueError(f"Permissão '{chave}' inválida em {raiz}.")
                regra[chave] = valor
            chave_raiz = os.path.normcase(str(raiz))
            if chave_raiz not in vistos:
                vistos.add(chave_raiz)
                normalizados.append(regra)
        return normalizados

    @classmethod
    def from_dict(cls, project_root, data):
        if not isinstance(data, dict):
            raise ValueError("Configuração de permissões inválida.")
        mode = data.get("mode", "project_confirm")
        if not isinstance(mode, str):
            raise ValueError("Modo de permissão inválido.")
        grants = data.get("grants", [])
        confirm_reads = data.get("confirm_reads", True)
        return cls(project_root, mode,
                   grants, confirm_reads)

    def to_dict(self) -> dict:
        return {
            "mode": self.mode,
            "grants": [dict(g) for g in self.grants],
            "confirm_reads": self.confirm_reads,
        }

    @property
    def requires_confirmation(self) -> bool:
        """Compatibilidade: confirmação exigida para operações de arquivo."""
        return self.requires_file_confirmation

    @property
    def requires_file_confirmation(self) -> bool:
        return self.mode in {"project_confirm", "computer_confirm"}

    @property
    def requires_command_confirmation(self) -> bool:
        return self.mode not in {"folders", "computer_auto"}

    @property
    def requires_read_confirmation(self) -> bool:
        return self.confirm_reads and self.mode != "project_auto"

    def _checar_bloqueado(self, destino: Path):
        if (destino.drive and
                os.path.normcase(destino.drive)
                == os.path.normcase(self._unidade_sistema)
                and destino.parent == Path(destino.anchor)):
            raise SandboxError(
                f"Arquivos na raiz do disco do sistema são protegidos: {destino}")
        if any(_dentro(destino, raiz) for raiz in self._bloqueados):
            raise SandboxError(
                f"Caminho crítico do Windows protegido: {destino}")

    def check_not_blocked(self, destino):
        """Aplica o bloqueio de caminhos críticos também a raízes virtuais."""
        self._checar_bloqueado(Path(destino))

    @staticmethod
    def _rejeitar_links(destino: Path, raiz: Path):
        atual = raiz
        for parte in destino.relative_to(raiz).parts:
            atual = atual / parte
            if atual.is_symlink() or (
                    hasattr(atual, "is_junction") and atual.is_junction()):
                raise SandboxError(f"Componente é link: {atual}")

    def _absoluto(self, texto: str) -> Path:
        if "\x00" in texto or ".." in PureWindowsPath(texto).parts:
            raise SandboxError("Caminho absoluto inválido.")
        if texto.startswith(("\\\\", "//")):
            raise SandboxError("Caminho de rede não é aceito.")
        caminho = Path(texto).expanduser()
        if not caminho.is_absolute():
            raise SandboxError(f"Caminho absoluto inválido: {texto}")
        if ":" in str(caminho).replace(caminho.anchor, "", 1):
            raise SandboxError("Caminho com ':' não é aceito (ADS do Windows).")

        unidade = Path(caminho.anchor)
        try:
            sandbox_unidade = Sandbox(unidade)
        except SandboxError as e:
            raise SandboxError(str(e)) from e
        relativo = caminho.relative_to(unidade).as_posix()
        destino = sandbox_unidade.resolve(relativo)
        self._rejeitar_links(caminho, unidade)
        return destino

    def _regra_para(self, destino: Path) -> FolderGrant | None:
        correspondentes = [
            regra for regra in self.grants
            if _dentro(destino, Path(regra["path"]))
        ]
        return max(correspondentes, key=lambda r: len(r["path"])) if correspondentes else None

    def resolve(self, caminho: str, operacao: str) -> Path:
        """Valida caminho e permissão da operação, devolvendo o destino absoluto."""
        if operacao not in OPERACOES:
            raise ValueError(f"Operação desconhecida: {operacao}")
        if not isinstance(caminho, str) or not caminho:
            raise SandboxError("Caminho vazio.")

        if caminho in (".", self.project.root.name):
            if operacao != "ler":
                raise SandboxError("Não é permitido operar sobre a raiz do projeto.")
            if self.mode == "folders":
                regra = self._regra_para(self.project.root)
                if not regra or not regra["read"]:
                    raise SandboxError("Leitura da raiz do projeto não autorizada.")
            return self.project.root

        if Path(caminho).is_absolute():
            if self.mode not in {"folders", "computer_confirm", "computer_auto"}:
                raise SandboxError("Caminho fora do projeto não autorizado.")
            destino = self._absoluto(caminho)
            self._checar_bloqueado(destino)
            if self.mode == "folders":
                regra = self._regra_para(destino)
                chave = _CHAVES_OPERACAO[operacao]
                if not regra or not regra[chave]:
                    raise SandboxError(
                        f"'{operacao}' não permitido nesta pasta: {destino}")
            return destino

        destino = self.project.resolve(caminho)
        self._checar_bloqueado(destino)
        if self.mode == "folders":
            regra = self._regra_para(destino)
            if regra:
                autorizado = regra[_CHAVES_OPERACAO[operacao]]
            else:
                autorizado = False
            if not autorizado:
                raise SandboxError(
                    f"'{operacao}' não permitido nesta pasta: {destino}")
        return destino
