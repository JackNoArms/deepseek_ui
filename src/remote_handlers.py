"""Handlers dos comandos remotos: projeto, vault, arquivos, envio, anexos.

O `MainWindow` herda deste mixin. Cada método aqui roda na thread da GUI
(o `RemoteServer` emite um sinal Qt com a operação e espera o retorno num
`threading.Event` — mesmo padrão do `agent_qt.py`), então pode tocar em
widget, projeto, `WorkspaceStore`, `Executor` e todo o resto sem se preocupar
com thread-safety.

A lista de operações é fechada em propósito. Não é um shell remoto — cada
comando do celular tem um nome fixo e um contrato pequeno, para o servidor
poder recusar qualquer coisa fora disso sem depender de permissão de arquivo.

Este módulo **não importa `window.py`**. Foi um acoplamento que derrubava o
processo no import dinâmico de `ChipAnexo` (PyQt6 sem `QApplication` crasha o
Windows com stack buffer overrun, não capturável por `except`). O contrato é:
se a janela tiver `_adicionar_chip_anexo`, o mixin chama; se não, é no-op.
"""

from __future__ import annotations

import base64
import binascii
import time
from pathlib import Path

from src import anexos
from src.anexos import Anexo, MAX_INLINE_BYTES
from src.permissions import MODOS, PermissionPolicy
from src.project import Project, historico_projetos
from src.sandbox import SandboxError
from src.session import ProjectSession
from src.vault import WorkspaceStore


def _store(project: Project, tipo: str) -> WorkspaceStore:
    """Store de projeto ou vault do projeto aberto. Espelha `MainWindow._store_workspace`."""
    if project is None:
        raise SandboxError("Nenhum projeto aberto.")
    if tipo == "projeto":
        return WorkspaceStore(project.root, project.root, project_tree=True)
    caminho = ProjectSession(project.root).vault_path()
    if not caminho or not Path(caminho).is_dir():
        raise SandboxError("Nenhum vault válido está vinculado ao projeto.")
    return WorkspaceStore(caminho, project.root, backup_prefix="_vault")


def _entries_dict(project: Project, tipo: str) -> list[dict]:
    """Árvore em formato JSON, pronta para o painel montar a coluna."""
    if project is None:
        return []
    if tipo == "projeto":
        entradas = WorkspaceStore(project.root, project.root,
                                  project_tree=True).entries()
    else:
        caminho = ProjectSession(project.root).vault_path()
        if not caminho or not Path(caminho).is_dir():
            return []
        entradas = WorkspaceStore(caminho, project.root,
                                  backup_prefix="_vault").entries()
    return [{"path": e.path, "is_dir": bool(e.is_dir)} for e in entradas]


def _sanitizar_nome(nome: str) -> str:
    """Só o nome do arquivo, sem diretórios nem caracteres estranhos.

    O celular manda o `name` que o navegador deu; pode vir com `..`, barra,
    caminho de rede. Aqui é puramente cosmético (vai virar parte do nome do
    temporário), mas a sanitização é mais barata que auditar depois.
    """
    base = Path(nome or "anexo").name
    ok = "".join(c for c in base if c.isalnum() or c in "._- ")
    return (ok.strip() or "anexo")[:80]


def _decidir_modo(rotulo: str, mime: str, tamanho: int) -> str:
    """Inline (texto colado) ou upload (resto). Mesma regra do `anexos.py`.

    Reusa a extensão conhecida do módulo de anexos, e cai no mime quando não
    reconhecer a extensão. Um `.py` de 30 KB continua indo inline mesmo se o
    navegador mentir o mime; um `image/png` com nome sem extensão ainda vira
    upload, porque é o que o `<input type=file>` do DeepSeek aceita.
    """
    sufixo = Path(rotulo).suffix.lower()
    if sufixo in anexos.EXT_TEXTO and tamanho <= MAX_INLINE_BYTES:
        return "inline"
    if (mime or "").lower().startswith("text/") and tamanho <= MAX_INLINE_BYTES:
        return "inline"
    return "upload"


def converter_anexos_json(itens: list) -> tuple[list[Anexo], list[str]]:
    """Itens `{rotulo, tipo_mime, dados_b64}` do celular → `Anexo`s.

    - **inline** (texto até `MAX_INLINE_BYTES`): decodifica como UTF-8 e
      cria `Anexo(modo='inline')`.
    - **upload** (imagem, binário, texto grande): grava num arquivo
      temporário em `_pasta_temp()` e cria `Anexo(modo='upload', temporario=True)`.

    Recusa item a item (payload vazio, base64 inválido) sem derrubar o lote.
    No máximo 8 itens.
    """
    convertidos, recusados = [], []
    for item in (itens or [])[:8]:
        if not isinstance(item, dict):
            recusados.append("item malformado")
            continue
        rotulo_bruto = str(item.get("rotulo") or "anexo")
        rotulo = _sanitizar_nome(rotulo_bruto)
        mime = str(item.get("tipo_mime") or "")
        b64 = item.get("dados_b64")
        if not isinstance(b64, str) or not b64:
            recusados.append(f"{rotulo}: sem dados")
            continue
        try:
            dados = base64.b64decode(b64, validate=True)
        except (binascii.Error, ValueError):
            recusados.append(f"{rotulo}: base64 inválido")
            continue
        if not dados:
            recusados.append(f"{rotulo}: vazio")
            continue

        modo = _decidir_modo(rotulo_bruto, mime, len(dados))
        if modo == "inline":
            try:
                texto = dados.decode("utf-8")
            except UnicodeDecodeError:
                modo = "upload"
        if modo == "upload":
            sufixo = Path(rotulo_bruto).suffix or ".bin"
            nome = (f"celular-{time.strftime('%Y%m%d-%H%M%S')}"
                    f"-{int(time.time() * 1000) % 1000}-{rotulo}{sufixo}")
            destino = anexos._pasta_temp() / nome
            try:
                destino.write_bytes(dados)
            except OSError as e:
                recusados.append(f"{rotulo}: {e}")
                continue
            convertidos.append(Anexo(rotulo, "upload", caminho=str(destino),
                                     temporario=True))
        else:
            convertidos.append(Anexo(rotulo, "inline", conteudo=texto))
    return convertidos, recusados


class RemoteHandlersMixin:
    """Métodos chamados pelo servidor remoto, sempre na thread da GUI.

    Cada um recebe kwargs vindos do JSON do celular e devolve um dict. Erros
    viram `{"erro": "..."}` — o servidor traduz para HTTP 4xx e o painel
    mostra o texto para o usuário.
    """

    # ---------------- projeto ----------------

    def _remote_list_projects(self) -> dict:
        """Projetos recentes + o aberto. Caminho absoluto (o celular não tem
        noção de CWD)."""
        recentes = historico_projetos()
        atual = str(self.project.root) if self.project else None
        if atual and atual not in recentes:
            recentes.insert(0, atual)
        return {
            "atual": atual,
            "nome_atual": self.project.nome if self.project else None,
            "recentes": recentes,
        }

    def _remote_open_project(self, caminho: str) -> dict:
        caminho = (caminho or "").strip()
        if not caminho:
            return {"erro": "caminho vazio"}
        if not Path(caminho).is_dir():
            return {"erro": "pasta não existe"}
        self._set_project(caminho)
        return {"ok": True, "atual": str(self.project.root) if self.project else None,
                "nome": self.project.nome if self.project else None}

    # ---------------- vault ----------------

    def _remote_list_vaults(self) -> dict:
        if self.project is None:
            return {"erro": "nenhum projeto aberto"}
        sessao = ProjectSession(self.project.root)
        vinculado = sessao.vault_path()
        return {
            "vinculado": vinculado,
            "padrao": str(self.project.root / "vault"),
        }

    def _remote_open_vault(self, caminho: str) -> dict:
        if self.project is None:
            return {"erro": "nenhum projeto aberto"}
        caminho = (caminho or "").strip()
        if not caminho or not Path(caminho).is_dir():
            return {"erro": "pasta do vault não existe"}
        try:
            from src.vault import garantir_vault
            selecionado = Path(caminho).resolve(strict=True)
            if selecionado == self.project.root:
                return {"erro": "a raiz do projeto não pode ser o vault"}
            novo = garantir_vault(selecionado, self.project.nome)
            if not ProjectSession(self.project.root).salvar_vault(str(novo)):
                return {"erro": "não consegui salvar o vínculo do vault"}
            self.project.vault_root = Path(novo)
            self._carregar_instrucoes_vault()
            return {"ok": True, "vinculado": str(novo)}
        except (OSError, SandboxError, ValueError) as e:
            return {"erro": str(e)}

    # ---------------- árvore ----------------

    def _remote_list_tree(self, tipo: str) -> dict:
        if tipo not in ("projeto", "vault"):
            return {"erro": "tipo inválido"}
        if self.project is None:
            return {"erro": "nenhum projeto aberto"}
        return {"tipo": tipo, "entries": _entries_dict(self.project, tipo)}

    # ---------------- arquivo ----------------

    def _remote_read_file(self, tipo: str, caminho: str) -> dict:
        if tipo not in ("projeto", "vault"):
            return {"erro": "tipo inválido"}
        if self.project is None:
            return {"erro": "nenhum projeto aberto"}
        try:
            store = _store(self.project, tipo)
            texto = store.read_text(caminho)
            return {"ok": True, "caminho": caminho, "conteudo": texto}
        except (OSError, SandboxError, ValueError) as e:
            return {"erro": str(e)}

    def _remote_write_file(self, tipo: str, caminho: str, conteudo: str,
                           criar: bool = False) -> dict:
        if tipo not in ("projeto", "vault"):
            return {"erro": "tipo inválido"}
        if self.project is None:
            return {"erro": "nenhum projeto aberto"}
        try:
            store = _store(self.project, tipo)
            store.write_text(caminho, conteudo or "", create=bool(criar))
            self._atualizar_arvore()
            if tipo == "vault":
                self._atualizar_arvore_vault()
            return {"ok": True, "caminho": caminho}
        except (OSError, SandboxError, ValueError) as e:
            return {"erro": str(e)}

    def _remote_delete_file(self, tipo: str, caminho: str) -> dict:
        if tipo not in ("projeto", "vault"):
            return {"erro": "tipo inválido"}
        if self.project is None:
            return {"erro": "nenhum projeto aberto"}
        try:
            store = _store(self.project, tipo)
            store.delete(caminho)
            self._atualizar_arvore()
            if tipo == "vault":
                self._atualizar_arvore_vault()
            return {"ok": True}
        except (OSError, SandboxError, ValueError) as e:
            return {"erro": str(e)}

    def _remote_new_folder(self, tipo: str, caminho: str) -> dict:
        if tipo not in ("projeto", "vault"):
            return {"erro": "tipo inválido"}
        if self.project is None:
            return {"erro": "nenhum projeto aberto"}
        try:
            store = _store(self.project, tipo)
            store.create_folder(caminho)
            self._atualizar_arvore()
            if tipo == "vault":
                self._atualizar_arvore_vault()
            return {"ok": True}
        except (OSError, SandboxError, ValueError) as e:
            return {"erro": str(e)}

    # ---------------- browse (para escolher pasta) ----------------

    def _remote_browse(self, caminho: str) -> dict:
        """Lista subpastas de um diretório, para o celular navegar até uma raiz.

        Só diretórios. Arquivos não interessam para escolher projeto/vault, e
        listar arquivo aqui seria só superfície de leitura sem uso.
        """
        alvo = (caminho or "").strip()
        if not alvo:
            alvo = str(Path.home())
        try:
            p = Path(alvo).expanduser().resolve(strict=True)
        except OSError:
            return {"erro": "pasta não encontrada"}
        if not p.is_dir():
            return {"erro": "não é pasta"}
        filhos = []
        try:
            for filho in sorted(p.iterdir(), key=lambda x: x.name.lower()):
                if filho.is_dir() and not filho.name.startswith("."):
                    filhos.append({"nome": filho.name, "caminho": str(filho)})
        except OSError as e:
            return {"erro": f"não consegui listar: {e}"}
        pai = str(p.parent) if p.parent != p else None
        return {"atual": str(p), "pai": pai, "filhos": filhos}

    # ---------------- chat ----------------

    def _remote_get_chat(self) -> dict:
        """Histórico + streaming atual do chat, direto do `ChatPanel`."""
        if not hasattr(self, "chat"):
            return {"messages": [], "streaming": None}
        return self.chat.historico_json()

    def _remote_send_message(self, texto: str, agente: bool = True) -> dict:
        """Envia mensagem pelo mesmo caminho do composer local.

        Reusa `_send`, que já cuida de fila, anexos pendentes e montagem do
        prompt. Coloca o texto no input, dispara e limpa — o usuário no PC vê a
        mensagem aparecer como se tivesse digitado, com os anexos que ele
        anexou pelo celular.
        """
        texto = (texto or "").strip()
        if not texto:
            return {"erro": "mensagem vazia"}
        if not self.controller.is_connected:
            return {"erro": "DeepSeek não está conectado"}
        if agente and not self.project:
            return {"erro": "o modo Agente precisa de um projeto aberto"}
        self.chk_agente.set_state(bool(agente))
        self.input.setPlainText(texto)
        self._send()
        return {"ok": True}

    def _remote_new_chat(self) -> dict:
        """Inicia uma conversa nova no DeepSeek, como o botão do PC.

        Reusa `MainWindow._new_chat`, que agenda `controller.new_chat` em
        background e devolve imediatamente. Se o app estiver ocupado (envio em
        andamento, agente rodando ou fila pendente), recusa com erro claro
        para o painel mostrar — o `_new_chat` local apenas escreveria no status.
        """
        gatilho = getattr(self, "_new_chat", None)
        if not callable(gatilho):
            return {"erro": "esta janela não suporta nova conversa remota"}
        if (getattr(self, "_envio_em_andamento", False)
                or getattr(self, "_agente", None) is not None
                or getattr(self, "_fila_mensagens", None)):
            return {"erro": "aguarde o envio e a fila terminarem antes de "
                            "criar outra conversa"}
        controller = getattr(self, "controller", None)
        if controller is None or not getattr(controller, "is_connected", False):
            return {"erro": "DeepSeek não está conectado"}
        gatilho()
        return {"ok": True}

    # ---------------- permissões ----------------

    def _remote_get_permissions(self) -> dict:
        """Política atual do projeto no mesmo formato que o PC usa.

        `modos` é a lista canônica aceita pelo `PermissionPolicy`, para o
        painel montar o `<select>` sem duplicar rótulos aqui.
        """
        if self.project is None:
            return {"erro": "nenhum projeto aberto"}
        politica = self.project.permissions
        return {
            "ok": True,
            "mode": politica.mode,
            "confirm_reads": bool(politica.confirm_reads),
            "grants": [dict(g) for g in politica.grants],
            "modos": sorted(MODOS),
        }

    def _remote_set_permissions(self, mode: str, grants: list,
                                 confirm_reads: bool) -> dict:
        """Substitui a política do projeto pelo payload do celular.

        Mesmo caminho do `_configurar_permissoes` no PC: valida via
        `PermissionPolicy.from_dict`, salva na sessão, atualiza `project` em
        memória. Recusa antes de gravar se o payload for inválido — nada de
        "meio aplicado".
        """
        if self.project is None:
            return {"erro": "nenhum projeto aberto"}
        try:
            politica = PermissionPolicy.from_dict(
                self.project.root,
                {"mode": mode, "grants": grants or [],
                 "confirm_reads": bool(confirm_reads)},
            )
        except (ValueError, SandboxError) as e:
            return {"erro": f"configuração recusada: {e}"}
        sessao = ProjectSession(self.project.root)
        if not sessao.salvar_permissoes(politica.to_dict()):
            return {"erro": "não consegui salvar as permissões deste projeto"}
        self.project.permissions = politica
        self.project.sandbox = politica.project
        feedback = getattr(self, "_atualizar_feedback_acesso", None)
        if callable(feedback):
            try:
                feedback()
            except Exception:
                pass
        return {
            "ok": True,
            "mode": politica.mode,
            "confirm_reads": bool(politica.confirm_reads),
            "grants": [dict(g) for g in politica.grants],
        }

    # ---------------- busca ----------------

    def _remote_buscar(self, termo: str, em: str | None = None,
                        ext: str | None = None) -> dict:
        if self.project is None:
            return {"erro": "nenhum projeto aberto"}
        try:
            texto = self.project.buscar(termo, em=em, ext=ext,
                                          max_achados=200,
                                          max_bytes=2_000_000)
            return {"ok": True, "resultado": texto}
        except (OSError, SandboxError) as e:
            return {"erro": str(e)}

    # ---------------- fila ----------------

    def _remote_cancel_queue(self, id: str = "") -> dict:
        """Cancela um item da fila (ainda não enviado)."""
        cancelar = getattr(self, "_cancelar_da_fila", None)
        if not callable(cancelar):
            return {"erro": "esta janela não tem fila"}
        if not cancelar(str(id or "")):
            return {"erro": "item não está mais na fila"}
        return {"ok": True}

    def _remote_edit_queue(self, id: str = "", texto: str = "") -> dict:
        """Troca o texto de um item que ainda está na fila."""
        editar = getattr(self, "_editar_texto_fila", None)
        if not callable(editar):
            return {"erro": "esta janela não tem fila"}
        if not (texto or "").strip():
            return {"erro": "texto vazio — para tirar da fila use cancelar"}
        if not editar(str(id or ""), str(texto)):
            return {"erro": "item não está mais na fila"}
        return {"ok": True}

    def _remote_clear_queue(self) -> dict:
        limpar = getattr(self, "_limpar_fila", None)
        if not callable(limpar):
            return {"erro": "esta janela não tem fila"}
        return {"ok": True, "cancelados": limpar()}

    # ---------------- decisão com anexo ----------------

    def _remote_decision_attach(self, id_card: str = "",
                                anexos_json: list | None = None) -> dict:
        """Guarda os anexos da resposta livre até a decisão ser respondida.

        O `RemoteServer.answer` vem logo depois; `_decisao_remota` busca os
        anexos por `id_card` e os entrega junto da escolha ao agente.
        """
        pendentes = getattr(self, "_decisoes_remotas", {})
        if id_card not in pendentes:
            return {"erro": "decisão já resolvida ou desconhecida"}
        if not isinstance(anexos_json, list) or not anexos_json:
            return {"erro": "sem anexos"}
        convertidos, recusados = converter_anexos_json(anexos_json)
        if not convertidos:
            return {"erro": "nenhum anexo aceito", "recusados": recusados}
        guardados = getattr(self, "_anexos_decisao_remota", None)
        if guardados is None:
            guardados = self._anexos_decisao_remota = {}
        for anterior in guardados.pop(id_card, []):
            anterior.descartar()
        guardados[id_card] = convertidos
        return {"ok": True,
                "adicionados": [a.rotulo for a in convertidos],
                "recusados": recusados}

    # ---------------- anexos ----------------

    def _remote_list_attachments(self) -> dict:
        """Anexos pendentes (os que ainda não foram enviados)."""
        pendentes = getattr(self, "_anexos", []) or []
        return {
            "anexos": [
                {"rotulo": a.rotulo, "modo": a.modo}
                for a in pendentes
            ],
        }

    def _remote_attach(self, anexos_json: list) -> dict:
        """Recebe anexos do celular e os adiciona à lista viva do PC.

        Cada item do JSON é `{"rotulo": nome, "tipo_mime": mime,
        "dados_b64": ...}`. O conteúdo decide o destino:

        - **inline** (texto até `MAX_INLINE_BYTES`): decodifica como UTF-8 e
          cria `Anexo(modo='inline')`. Vai colado no rodapé do próximo envio.
        - **upload** (imagem, binário, texto grande): grava num arquivo
          temporário em `_pasta_temp()` e cria `Anexo(modo='upload', temporario=True)`.

        Recusa payload vazio ou base64 inválido item a item — não derruba a
        rodada inteira por um anexo ruim.

        O chip visual é criado por `_adicionar_chip_anexo(anexo)` **se existir**.
        """
        if not isinstance(anexos_json, list) or not anexos_json:
            return {"erro": "sem anexos"}
        if not hasattr(self, "_anexos"):
            return {"erro": "janela sem lista de anexos"}

        convertidos, recusados = converter_anexos_json(anexos_json)
        adicionados = []
        for anexo in convertidos:
            self._anexos.append(anexo)
            gancho = getattr(self, "_adicionar_chip_anexo", None)
            if callable(gancho):
                try:
                    gancho(anexo)
                except Exception:
                    pass
            adicionados.append({"rotulo": anexo.rotulo, "modo": anexo.modo})

        if not adicionados:
            return {"erro": "nenhum anexo aceito", "recusados": recusados}
        return {"ok": True, "adicionados": adicionados, "recusados": recusados}
