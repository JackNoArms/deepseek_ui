"""Sessão do projeto: qual conversa do DeepSeek pertence a esta pasta.

Cada projeto tem a sua conversa. Guardando a URL dentro do próprio projeto, ao
reabrir o app no dia seguinte dá para voltar exatamente para onde você parou —
com o histórico e o contexto que o modelo já tem daquele código.

Fica em `.deepseek_ui/session.json`, junto dos backups, e vai para o
`.gitignore`: é estado da sua máquina, não do repositório.
"""

import json
import os
import re

# Conversa do DeepSeek: .../a/chat/s/<id>. A home (chat.deepseek.com) não serve —
# ela não aponta para conversa nenhuma, e salvá-la faria o app "retomar" o vazio.
CHAT_URL_RE = re.compile(r"chat\.deepseek\.com/a/chat/s/[0-9a-f-]+", re.IGNORECASE)

PASTA = ".deepseek_ui"


def e_conversa(url: str) -> bool:
    return bool(url and CHAT_URL_RE.search(url))


class ProjectSession:
    def __init__(self, raiz):
        self.dir = os.path.join(str(raiz), PASTA)
        self.path = os.path.join(self.dir, "session.json")

    def _ler(self) -> dict:
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                dados = json.load(f)
                return dados if isinstance(dados, dict) else {}
        except (OSError, json.JSONDecodeError):
            return {}

    def _gravar(self, mudancas: dict) -> bool:
        dados = self._ler()
        dados.update(mudancas)
        try:
            os.makedirs(self.dir, exist_ok=True)
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(dados, f, ensure_ascii=False, indent=2)
            return True
        except OSError:
            return False

    # ---------------- conversa ----------------

    def vault_path(self) -> str | None:
        """Pasta do vault associada a este projeto, se houver."""
        path = self._ler().get("vault_path")
        return path if isinstance(path, str) and path else None

    def salvar_vault(self, path: str) -> bool:
        """Vincula o vault escolhido pelo usuário a este projeto."""
        return self._gravar({"vault_path": os.path.abspath(path)})

    def permissoes(self) -> dict:
        dados = self._ler().get("permissions")
        return dados if isinstance(dados, dict) else {}

    def salvar_permissoes(self, permissoes: dict) -> bool:
        """Persiste a política de acesso sem sobrescrever URL ou vault."""
        if not isinstance(permissoes, dict):
            raise TypeError("As permissões precisam ser um objeto.")
        return self._gravar({"permissions": permissoes})

    def formato_resposta(self) -> str:
        formato = self._ler().get("response_format")
        return formato if formato in ("markdown", "json", "xml") else "markdown"

    def salvar_formato_resposta(self, formato: str) -> bool:
        if formato not in ("markdown", "json", "xml"):
            raise ValueError("Formato de resposta desconhecido.")
        return self._gravar({"response_format": formato})

    def sondas_formato(self) -> dict:
        sondas = self._ler().get("format_probes")
        sondas = sondas if isinstance(sondas, dict) else {}
        resultado = {}
        for formato in ("json", "xml"):
            contagem = sondas.get(formato)
            if not isinstance(contagem, dict):
                contagem = {}
            testes = contagem.get("tests", 0)
            validas = contagem.get("valid", 0)
            if (not isinstance(testes, int) or isinstance(testes, bool)
                    or not isinstance(validas, int) or isinstance(validas, bool)):
                testes, validas = 0, 0
            testes = max(0, testes)
            validas = min(testes, max(0, validas))
            resultado[formato] = {"tests": testes, "valid": validas}
        return resultado

    def registrar_sonda_formato(self, formato: str, valida: bool) -> bool:
        if formato not in ("json", "xml"):
            raise ValueError("Sondas só são suportadas para JSON e XML.")
        if not isinstance(valida, bool):
            raise TypeError("O resultado da sonda precisa ser booleano.")
        sondas = self.sondas_formato()
        sondas[formato]["tests"] += 1
        sondas[formato]["valid"] += int(valida)
        return self._gravar({"format_probes": sondas})

    def url(self) -> str | None:
        guardada = self._ler().get("deepseek_url")
        return guardada if e_conversa(guardada) else None

    def salvar_url(self, url: str, regras_enviadas: bool = True):
        """Só grava URL de conversa de verdade. Home não conta."""
        if not e_conversa(url):
            return
        if url == self._ler().get("deepseek_url"):
            return  # nada mudou; evita reescrever o arquivo a cada resposta
        self._gravar({"deepseek_url": url, "regras_enviadas": bool(regras_enviadas)})

    def regras_enviadas(self) -> bool:
        """As regras de formato já foram mandadas nessa conversa?

        Evita reenviar o bloco inteiro ao retomar — ele já está no histórico.
        """
        return bool(self._ler().get("regras_enviadas"))

    def marcar_regras_enviadas(self):
        self._gravar({"regras_enviadas": True})

    def esquecer(self):
        """Desliga o projeto da conversa (usado ao começar uma nova)."""
        self._gravar({"deepseek_url": None, "regras_enviadas": False})
