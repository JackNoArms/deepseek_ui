"""Habilidades (skills) no padrão Agent Skills.

Cada skill vive em ``skills/<slug>/SKILL.md`` com frontmatter mínimo:
``name`` e ``description``. O corpo é Markdown livre — fases numeradas,
portões 🛑, antipadrões etc. Esse formato é o mesmo usado por Claude Code,
Codex, Cline e outras ferramentas que falam "Agent Skills".

O estado do app (habilitada) fica separado, em
``.deepseek_ui/skills_state.json``, para o ``SKILL.md`` continuar portátil
entre agentes.

**Migração.** Arquivos ``skills/<slug>.md`` no formato antigo (v1:
frontmatter com ``nome``/``descricao``/``categoria``/``habilitada``/``icone``)
são convertidos automaticamente na primeira carga e movidos para
``.deepseek_ui/backups/skills-migration/``. Idempotente: rodar duas vezes
não duplica nem sobrescreve.

**Bootstrap de defaults.** Na primeira carga de cada projeto, as skills
padrão em ``assets/skills_default/`` (que viajam com o app) são copiadas
para ``<projeto>/skills/``. Não sobrescreve skill existente; skill padrão
que o usuário apagou não é ressuscitada (registro em ``defaults_aplicados``
no state). Idempotente: só roda uma vez por slug.
"""

from __future__ import annotations

import json
import re
import shutil
import tempfile
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import yaml

from src.caminhos import recurso


SKILLS_DIR_NAME = "skills"
STATE_DIR_NAME = ".deepseek_ui"
STATE_FILE_NAME = "skills_state.json"
BACKUP_DIR_PARTS = (STATE_DIR_NAME, "backups", "skills-migration")
DEFAULTS_DIR_REL = Path("assets") / "skills_default"
STATE_VERSION = 1

# Importação: tetos para não copiar um repositório inteiro por engano.
LIMITE_IMPORTACAO_BYTES = 20_000_000
LIMITE_IMPORTACAO_ARQUIVOS = 2_000
PADROES_IGNORADOS = (".git", "__pycache__", "node_modules", ".DS_Store",
                     "*.pyc", ".venv")

_SLUG_RE = re.compile(r"[^a-z0-9]+")
_ACENTOS = str.maketrans(
    "áàãâäéèêëíìîïóòõôöúùûüçñÁÀÃÂÄÉÈÊËÍÌÎÏÓÒÕÔÖÚÙÛÜÇÑ",
    "aaaaaeeeeiiiiooooouuuucnaaaaaeeeeiiiiooooouuuucn",
)


def _default_defaults_dir() -> Optional[Path]:
    """``assets/skills_default`` relativo à raiz do app (``src/../assets``).

    Retorna ``None`` se o diretório não existe — desativa o bootstrap.
    """
    candidato = recurso(*DEFAULTS_DIR_REL.parts)
    return candidato if candidato.is_dir() else None


@dataclass
class Skill:
    """Uma habilidade. ``slug`` identifica a pasta em disco.

    ``name`` e ``description`` vêm do frontmatter do ``SKILL.md``;
    ``conteudo`` é o corpo (pós-frontmatter); ``habilitada`` vem do
    ``skills_state.json`` (estado do app).
    """

    slug: str
    name: str
    description: str = ""
    conteudo: str = ""
    habilitada: bool = False


@dataclass
class ResultadoImportacao:
    """O que `SkillsRepo.importar` fez: skills criadas e o que ficou de fora."""

    importadas: list[Skill] = field(default_factory=list)
    ignorados: list[str] = field(default_factory=list)


class SkillsRepo:
    """Repositório de habilidades baseado em uma pasta ``skills/`` por projeto.

    Contrato público (compatível com a v1):

    - ``load()`` — bootstrapa defaults, migra o formato v1 e lê tudo do disco
    - ``all()``, ``habilitadas()``, ``by_slug(slug)`` — consulta
    - ``save(skill)``, ``delete(slug)`` — escrita
    - ``novo_slug(nome)`` — gera slug único
    - ``set_habilitada(slug, bool)`` — atalho que mexe só no state

    ``defaults_dir`` (opcional) aponta para uma pasta com subpastas de skills
    padrão a copiar no primeiro ``load()``. ``None`` desativa o bootstrap.
    Se omitido, tenta ``assets/skills_default`` ao lado de ``src/``.
    """

    def __init__(self, base_dir: Path | str,
                 defaults_dir: Path | str | None = None,
                 *,
                 bootstrap: bool = True):
        self.base_dir = Path(base_dir)
        self.skills_dir = self.base_dir / SKILLS_DIR_NAME
        self.state_file = self.base_dir / STATE_DIR_NAME / STATE_FILE_NAME
        if not bootstrap:
            self.defaults_dir: Optional[Path] = None
        elif defaults_dir is None:
            self.defaults_dir = _default_defaults_dir()
        else:
            self.defaults_dir = Path(defaults_dir)
        self._skills: list[Skill] = []
        self._loaded = False

    # ---- IO ---------------------------------------------------------

    def load(self) -> list[Skill]:
        """(Re)carrega todas as habilidades.

        Ordem: migra v1→v2 primeiro (preserva conteúdo do usuário), depois
        bootstrapa defaults faltantes (só se ainda não processados).
        """
        self._migrate_legacy()
        self._bootstrap_defaults()
        state = self._load_state()
        carregadas: list[Skill] = []
        if self.skills_dir.is_dir():
            for path in sorted(self.skills_dir.iterdir()):
                if not path.is_dir():
                    continue
                if not (path / "SKILL.md").is_file():
                    continue
                skill = self._read_skill(path, state)
                if skill is not None:
                    carregadas.append(skill)
        self._skills = carregadas
        self._loaded = True
        return list(carregadas)

    def _read_skill(self, skill_dir: Path, state: dict) -> Optional[Skill]:
        path = skill_dir / "SKILL.md"
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            return None
        meta, body = _split_frontmatter(text)
        slug = skill_dir.name
        name = _coerce_str(meta.get("name")) or slug
        description = _coerce_str(meta.get("description"))
        entry = state.get("skills", {}).get(slug, {})
        habilitada = bool(entry.get("habilitada", False)) if isinstance(entry, dict) else False
        return Skill(
            slug=slug,
            name=name,
            description=description,
            conteudo=body,
            habilitada=habilitada,
        )

    def save(self, skill: Skill) -> None:
        """Grava o ``SKILL.md`` e atualiza o estado (habilitada) no JSON."""
        self.skills_dir.mkdir(parents=True, exist_ok=True)
        skill_dir = self.skills_dir / skill.slug
        skill_dir.mkdir(parents=True, exist_ok=True)
        meta = {
            "name": skill.name.strip() or skill.slug,
            "description": skill.description,
        }
        corpo = skill.conteudo.rstrip() + "\n" if skill.conteudo.strip() else ""
        text = _join_frontmatter(meta) + "\n\n" + corpo
        (skill_dir / "SKILL.md").write_text(text, encoding="utf-8")

        state = self._load_state()
        entry = state.setdefault("skills", {}).setdefault(skill.slug, {})
        entry["habilitada"] = bool(skill.habilitada)
        entry["atualizado"] = _iso_now()
        self._save_state(state)

        for i, existente in enumerate(self._skills):
            if existente.slug == skill.slug:
                self._skills[i] = skill
                return
        self._skills.append(skill)
        self._skills.sort(key=lambda s: s.slug)

    def delete(self, slug: str) -> None:
        """Apaga a pasta da skill e remove do state.

        O ``slug`` continua em ``defaults_aplicados`` (se já estava) — não é
        ressuscitado pelo bootstrap.
        """
        skill_dir = self.skills_dir / slug
        if skill_dir.is_dir():
            try:
                shutil.rmtree(skill_dir)
            except OSError:
                pass
        state = self._load_state()
        if slug in state.get("skills", {}):
            del state["skills"][slug]
            self._save_state(state)
        self._skills = [s for s in self._skills if s.slug != slug]

    def set_habilitada(self, slug: str, habilitada: bool) -> Optional[Skill]:
        """Liga/desliga sem tocar no ``SKILL.md``. Devolve a skill ou None."""
        skill = self.by_slug(slug)
        if skill is None:
            return None
        skill.habilitada = habilitada
        state = self._load_state()
        entry = state.setdefault("skills", {}).setdefault(slug, {})
        entry["habilitada"] = habilitada
        entry["atualizado"] = _iso_now()
        self._save_state(state)
        return skill

    # ---- importação --------------------------------------------------

    def importar(self, origem: Path | str) -> "ResultadoImportacao":
        """Importa skills de uma pasta, arquivo ``.md`` ou ``.zip``/``.skill``.

        - Pasta com ``SKILL.md``: copia a pasta inteira (arquivos de apoio
          vão junto).
        - Pasta sem ``SKILL.md`` (ex.: ``~/.claude/skills``): importa cada
          subpasta que tiver ``SKILL.md`` (até 3 níveis).
        - ``SKILL.md`` solto: importa a pasta onde ele está.
        - Outro ``.md``: vira uma skill nova com o conteúdo do arquivo.
        - ``.zip``/``.skill``: extrai num temporário (sem sair da pasta de
          destino) e trata como pasta.

        Nunca sobrescreve: slug repetido ganha sufixo ``-2``, ``-3``…
        Skills importadas entram desabilitadas, como as padrão.
        """
        resultado = ResultadoImportacao()
        caminho = Path(origem)
        try:
            if caminho.is_dir():
                self._importar_diretorio(caminho, resultado)
            elif caminho.is_file():
                sufixo = caminho.suffix.lower()
                if sufixo in (".zip", ".skill"):
                    self._importar_zip(caminho, resultado)
                elif caminho.name.lower() == "skill.md":
                    self._importar_pasta_skill(caminho.parent, resultado)
                elif sufixo in (".md", ".markdown", ".txt"):
                    texto = caminho.read_text(encoding="utf-8", errors="replace")
                    skill = self.importar_texto(texto, nome_sugerido=caminho.stem)
                    if skill is None:
                        resultado.ignorados.append(f"{caminho.name}: vazio")
                    else:
                        resultado.importadas.append(skill)
                else:
                    resultado.ignorados.append(
                        f"{caminho.name}: formato não suportado")
            else:
                resultado.ignorados.append(f"{caminho}: não encontrado")
        except (OSError, zipfile.BadZipFile, ValueError) as e:
            resultado.ignorados.append(f"{caminho.name}: {e}")
        if resultado.importadas:
            self.load()
        return resultado

    def importar_texto(self, texto: str,
                       nome_sugerido: str | None = None) -> Optional[Skill]:
        """Cria uma skill a partir de Markdown (com ou sem frontmatter).

        O nome vem do frontmatter ``name``, senão do primeiro título ``#``,
        senão de ``nome_sugerido``.
        """
        texto = (texto or "").replace("\r\n", "\n").strip()
        if not texto:
            return None
        meta, corpo = _split_frontmatter(texto)
        nome = _coerce_str(meta.get("name") or meta.get("nome")).strip()
        if not nome:
            titulo = re.search(r"^#\s+(.+)$", corpo, re.MULTILINE)
            nome = titulo.group(1).strip() if titulo else ""
        nome = nome or (nome_sugerido or "").strip() or "Habilidade importada"
        descricao = _coerce_str(
            meta.get("description") or meta.get("descricao")).strip()
        if not self._loaded:
            self.load()
        skill = Skill(
            slug=self.novo_slug(nome),
            name=nome,
            description=descricao,
            conteudo=corpo.strip("\n"),
            habilitada=False,
        )
        self.save(skill)
        return skill

    def _importar_diretorio(self, pasta: Path, resultado) -> None:
        if (pasta / "SKILL.md").is_file():
            self._importar_pasta_skill(pasta, resultado)
            return
        achadas = sorted(
            {p.parent for p in pasta.glob("SKILL.md")}
            | {p.parent for p in pasta.glob("*/SKILL.md")}
            | {p.parent for p in pasta.glob("*/*/SKILL.md")}
            | {p.parent for p in pasta.glob("*/*/*/SKILL.md")})
        if not achadas:
            resultado.ignorados.append(f"{pasta.name}: nenhum SKILL.md encontrado")
            return
        for skill_dir in achadas:
            self._importar_pasta_skill(skill_dir, resultado)

    def _importar_pasta_skill(self, pasta: Path, resultado) -> None:
        origem = pasta.resolve()
        try:
            origem.relative_to(self.skills_dir.resolve())
            resultado.ignorados.append(f"{pasta.name}: já está neste projeto")
            return
        except ValueError:
            pass
        arquivos = [p for p in origem.rglob("*")
                    if p.is_file() and not _ignorar_na_copia(p.relative_to(origem))]
        tamanho = sum(p.stat().st_size for p in arquivos)
        if tamanho > LIMITE_IMPORTACAO_BYTES:
            resultado.ignorados.append(
                f"{pasta.name}: pasta grande demais ({tamanho // 1_000_000} MB)")
            return
        texto = (origem / "SKILL.md").read_text(encoding="utf-8", errors="replace")
        meta, _ = _split_frontmatter(texto)
        nome = _coerce_str(meta.get("name")).strip() or pasta.name
        if not self._loaded:
            self.load()
        slug = self.novo_slug(_slugify(pasta.name) or nome)
        destino = self.skills_dir / slug
        self.skills_dir.mkdir(parents=True, exist_ok=True)
        shutil.copytree(
            origem, destino,
            ignore=shutil.ignore_patterns(*PADROES_IGNORADOS))
        state = self._load_state()
        entry = state.setdefault("skills", {}).setdefault(slug, {})
        entry["habilitada"] = False
        entry["atualizado"] = _iso_now()
        entry["importada_de"] = str(origem)
        self._save_state(state)
        skill = self._read_skill(destino, state)
        if skill is not None:
            self._skills.append(skill)
            self._skills.sort(key=lambda s: s.slug)
            resultado.importadas.append(skill)

    def _importar_zip(self, arquivo: Path, resultado) -> None:
        with zipfile.ZipFile(arquivo) as zf:
            membros = [m for m in zf.infolist() if not m.is_dir()]
            if len(membros) > LIMITE_IMPORTACAO_ARQUIVOS:
                raise ValueError("arquivos demais no zip")
            if sum(m.file_size for m in membros) > LIMITE_IMPORTACAO_BYTES:
                raise ValueError("zip grande demais")
            with tempfile.TemporaryDirectory(prefix="skills-import-") as tmp:
                base = Path(tmp).resolve()
                for membro in membros:
                    alvo = (base / membro.filename).resolve()
                    try:
                        alvo.relative_to(base)
                    except ValueError:
                        raise ValueError(
                            f"caminho inseguro no zip: {membro.filename}")
                    if (membro.external_attr >> 16) & 0o170000 == 0o120000:
                        continue  # symlink: ignorado
                    alvo.parent.mkdir(parents=True, exist_ok=True)
                    with zf.open(membro) as src, open(alvo, "wb") as dst:
                        shutil.copyfileobj(src, dst)
                antes = len(resultado.importadas)
                self._importar_diretorio(base, resultado)
                if len(resultado.importadas) == antes and not resultado.ignorados:
                    resultado.ignorados.append(
                        f"{arquivo.name}: nenhum SKILL.md encontrado")

    # ---- consulta ---------------------------------------------------

    def all(self) -> list[Skill]:
        if not self._loaded:
            self.load()
        return list(self._skills)

    def habilitadas(self) -> list[Skill]:
        return [s for s in self.all() if s.habilitada]

    def by_slug(self, slug: str) -> Optional[Skill]:
        for s in self.all():
            if s.slug == slug:
                return s
        return None

    def novo_slug(self, nome: str) -> str:
        """Gera um slug único a partir de ``nome`` (sufixo ``-2``, ``-3``...)."""
        base = _slugify(nome) or "skill"
        existentes = {s.slug for s in self._skills}
        if base not in existentes and not (self.skills_dir / base).exists():
            return base
        i = 2
        while f"{base}-{i}" in existentes or (self.skills_dir / f"{base}-{i}").exists():
            i += 1
        return f"{base}-{i}"

    # ---- state ------------------------------------------------------

    def _load_state(self) -> dict:
        if not self.state_file.exists():
            return {"version": STATE_VERSION, "skills": {}}
        try:
            raw = self.state_file.read_text(encoding="utf-8")
            data = json.loads(raw)
        except (OSError, json.JSONDecodeError):
            return {"version": STATE_VERSION, "skills": {}}
        if not isinstance(data, dict):
            return {"version": STATE_VERSION, "skills": {}}
        data.setdefault("version", STATE_VERSION)
        if not isinstance(data.get("skills"), dict):
            data["skills"] = {}
        if not isinstance(data.get("defaults_aplicados"), list):
            data["defaults_aplicados"] = []
        return data

    def _save_state(self, state: dict) -> None:
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        text = json.dumps(state, indent=2, ensure_ascii=False)
        self.state_file.write_text(text + "\n", encoding="utf-8")

    # ---- bootstrap de defaults --------------------------------------

    def _bootstrap_defaults(self) -> None:
        """Copia skills padrão para o projeto na primeira carga de cada slug.

        Regras:
        - Uma vez por slug: depois de processado, ``slug`` vai para
          ``defaults_aplicados`` no state e nunca é reavaliado. Isso evita
          que uma skill apagada pelo usuário seja ressuscitada.
        - Não sobrescreve ``SKILL.md`` que já existe (o usuário manda).
        - ``habilitada`` não é tocada; skill nova entra como ``False`` (default).
        """
        if self.defaults_dir is None or not self.defaults_dir.is_dir():
            return
        state = self._load_state()
        aplicados = set(state.get("defaults_aplicados") or [])
        mudou = False

        for src_dir in sorted(self.defaults_dir.iterdir()):
            if not src_dir.is_dir():
                continue
            slug = src_dir.name
            if slug in aplicados:
                continue
            aplicados.add(slug)
            mudou = True
            dst_path = self.skills_dir / slug / "SKILL.md"
            if dst_path.exists():
                continue
            src_path = src_dir / "SKILL.md"
            if not src_path.is_file():
                continue
            try:
                (self.skills_dir / slug).mkdir(parents=True, exist_ok=True)
                shutil.copy2(src_path, dst_path)
            except OSError:
                pass

        if mudou:
            state["defaults_aplicados"] = sorted(aplicados)
            self._save_state(state)

    # ---- migração ---------------------------------------------------

    def _migrate_legacy(self) -> None:
        """Converte ``skills/<slug>.md`` (v1) em ``skills/<slug>/SKILL.md`` (v2).

        Idempotente: se já existe ``<slug>/SKILL.md``, move o ``.md`` para o
        backup sem tocar no destino. O ``.md`` original sempre é movido para
        ``.deepseek_ui/backups/skills-migration/``. Se o slug já tiver entrada
        no state, o valor de ``habilitada`` do state **vence** (não sobrescreve).
        """
        if not self.skills_dir.is_dir():
            return
        legados = sorted(self.skills_dir.glob("*.md"))
        if not legados:
            return
        backup_dir = self.base_dir.joinpath(*BACKUP_DIR_PARTS)
        try:
            backup_dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            return
        state = self._load_state()
        mudou_state = False

        for old_path in legados:
            slug = old_path.stem
            if not slug:
                continue
            target_dir = self.skills_dir / slug
            target_path = target_dir / "SKILL.md"

            if target_path.exists():
                _mover_para_backup(old_path, backup_dir)
                continue

            try:
                old_text = old_path.read_text(encoding="utf-8")
            except OSError:
                continue

            meta, body = _split_frontmatter(old_text)
            name = (_coerce_str(meta.get("nome"))
                    or _coerce_str(meta.get("name"))
                    or slug)
            description = (_coerce_str(meta.get("descricao"))
                          or _coerce_str(meta.get("description")))
            habilitada_legado = bool(meta.get("habilitada", False))

            try:
                target_dir.mkdir(parents=True, exist_ok=True)
                novo_meta = {"name": name, "description": description}
                corpo = body.strip() + "\n" if body.strip() else ""
                novo_text = _join_frontmatter(novo_meta) + "\n\n" + corpo
                target_path.write_text(novo_text, encoding="utf-8")
            except OSError:
                continue

            skills_state = state.setdefault("skills", {})
            if slug not in skills_state or not isinstance(skills_state[slug], dict):
                skills_state[slug] = {"habilitada": habilitada_legado}
                mudou_state = True
            entry = skills_state[slug]
            entry.setdefault("atualizado", _iso_now())

            _mover_para_backup(old_path, backup_dir)

        if mudou_state:
            self._save_state(state)


# ---- helpers -------------------------------------------------------

def _ignorar_na_copia(rel: Path) -> bool:
    return any(parte in (".git", "__pycache__", "node_modules", ".venv")
               or parte.endswith(".pyc") or parte == ".DS_Store"
               for parte in rel.parts)


def _slugify(nome: str) -> str:
    s = (nome or "").strip().lower().translate(_ACENTOS)
    s = _SLUG_RE.sub("-", s)
    return s.strip("-")


def _coerce_str(valor: object) -> str:
    if valor is None:
        return ""
    return str(valor)


def _iso_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _mover_para_backup(old_path: Path, backup_dir: Path) -> None:
    destino = backup_dir / old_path.name
    if destino.exists():
        stem = destino.stem
        suffix = destino.suffix
        i = 2
        while destino.exists():
            destino = backup_dir / f"{stem}-{i}{suffix}"
            i += 1
    try:
        old_path.replace(destino)
    except OSError:
        pass


def _split_frontmatter(text: str) -> tuple[dict, str]:
    """Separa frontmatter YAML do corpo.

    Retorna ``({}, text)`` se não houver bloco ``---`` válido ou se o YAML
    falhar ao parsear — o corpo é preservado integralmente nesse caso.
    """
    if not text.startswith("---"):
        return {}, text
    linhas = text.split("\n")
    if len(linhas) < 2 or linhas[0].strip() != "---":
        return {}, text
    fim = None
    for i in range(1, len(linhas)):
        if linhas[i].strip() == "---":
            fim = i
            break
    if fim is None:
        return {}, text
    corpo_fm = "\n".join(linhas[1:fim])
    corpo = "\n".join(linhas[fim + 1:])
    try:
        meta = yaml.safe_load(corpo_fm) or {}
    except yaml.YAMLError:
        return {}, text
    if not isinstance(meta, dict):
        return {}, text
    return meta, corpo


def _join_frontmatter(meta: dict) -> str:
    """Serializa o dicionário na ordem canônica ``name, description``.

    ``yaml.safe_dump`` cuida de strings multi-linha, caracteres especiais e
    unicode. Ordem fixa ajuda no diff e na leitura.
    """
    ordenado = {
        "name": _coerce_str(meta.get("name")),
        "description": _coerce_str(meta.get("description")),
    }
    corpo = yaml.safe_dump(
        ordenado,
        allow_unicode=True,
        sort_keys=False,
        default_flow_style=False,
    )
    return "---\n" + corpo + "---"
