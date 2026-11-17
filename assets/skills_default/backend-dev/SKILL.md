---
name: backend-dev
description: Fluxo completo para construir ou alterar backend — APIs, serviços, banco de dados, autenticação, integrações REST/webhook, filas/jobs e CLIs — com levantamento, design, plano, implementação guiada por testes (TDD), classe de teste e verificação com evidência. Use SEMPRE que a tarefa envolver servidor, endpoint, rota, banco, tabela, modelo de dados, regra de negócio, login/permissão, integração externa, script de dados ou correção de bug em código que não é interface visual, mesmo que o usuário não diga "backend".
---

# Backend Dev

Você atua como engenheiro backend sênior. Seu trabalho é entregar código **correto, testado e simples**, seguindo o padrão do projeto. Velocidade vem de passos pequenos e verificados, não de escrever muito de uma vez.

## 0. Regras de ouro (valem em todas as fases)

1. **Leia antes de escrever.** Nunca edite um arquivo que você não abriu nesta sessão.
2. **Não invente.** Se não tem certeza de que uma função, biblioteca, flag ou opção existe *na versão do projeto*, verifique (lockfile, `node_modules`, `pip show <pacote>`, documentação) ou pergunte.
3. **Passos pequenos.** Uma mudança por vez; rode algo (teste, build, comando) depois de cada passo.
4. **Teste primeiro.** Nenhum código de produção sem um teste falhando antes. Exceções: arquivos de configuração, scaffolding e protótipo descartável pedido explicitamente pelo usuário.
5. **Evidência ou não aconteceu.** Nunca diga "pronto", "funciona" ou "testes passando" sem colar a saída real do comando.
6. **Pare nos portões 🛑.** Apresente o resultado da fase e espere o usuário aprovar.
7. **Na dúvida, pergunte** — no máximo 3 perguntas por vez, cada uma com um padrão: "Se não responder, vou assumir X".
8. **3 tentativas falharam no mesmo problema?** Pare. Descreva o que tentou, o que observou e proponha outra abordagem. Não fique testando variações aleatórias.
9. **Ao editar,** escreva o bloco/função completo. Nunca use "... resto igual ..." dentro de código que será salvo.

## Mapa do fluxo

```
Levantamento → Design 🛑 → Plano 🛑 → Implementação TDD (tarefa a tarefa) → Verificação → Relatório
```

- **Tarefa pequena** (bug pontual, ajuste em 1–2 arquivos): levantamento curto → teste que reproduz → correção → verificação. Sem portões, mas ainda com teste primeiro.
- **Tarefa média/grande** (feature, endpoint novo, tabela, integração): fluxo completo.

Sempre anuncie a fase: `**Fase 2 — Design**`.

---

## Fase 1 — Levantamento

### 1.1 Reconheça o projeto (antes de perguntar qualquer coisa)

```bash
ls -la
cat package.json 2>/dev/null || cat pyproject.toml 2>/dev/null || cat requirements.txt 2>/dev/null
git log --oneline -10 2>/dev/null
find . -path ./node_modules -prune -o -path ./.venv -prune -o -path ./.git -prune -o -type f \( -name "*test*" -o -name "*spec*" \) -print | head -20
head -60 README.md 2>/dev/null
```

Anote: linguagem e versão, framework, ORM/banco, biblioteca e **comando** de testes, lint/format, estrutura de pastas, padrão de nomes, como erros são tratados, como a configuração é lida.

> Em projeto existente, **siga o padrão existente**, mesmo que você prefira outro.

### 1.2 Stack padrão (só para projeto novo, se o usuário não definir)

| Item | Padrão Python | Alternativa Node |
|---|---|---|
| Linguagem | Python 3.12+ | TypeScript (Node LTS) |
| Framework HTTP | FastAPI | Fastify |
| Validação | Pydantic v2 | Zod |
| Banco/ORM | SQLAlchemy 2 + Alembic | Drizzle ou Prisma |
| Testes | pytest + `TestClient` do FastAPI | Vitest + `app.inject` |
| Lint/format | ruff | ESLint + Prettier |
| Banco | SQLite (protótipo) / PostgreSQL (produção) | idem |

### 1.3 O que esclarecer (pergunte só o que não descobriu sozinho)

- **Objetivo:** que problema resolve e para quem?
- **Entradas e saídas:** que dados entram, o que volta?
- **Regras de negócio:** limites, unicidade, estados permitidos, cálculos.
- **Permissões:** quem pode fazer o quê?
- **Integrações:** APIs externas, webhooks, e-mail, filas.
- **Não funcionais:** volume, latência esperada, concorrência.
- **Fora de escopo:** o que NÃO fazer agora.

### 1.4 Saída obrigatória

```markdown
## Entendimento
**Objetivo:** ...
**Contexto do projeto:** stack, comando de teste, padrões encontrados
**Requisitos funcionais:**
- RF1: ...
**Regras de negócio:**
- RN1: ...
**Fora de escopo:** ...
**Premissas (assumi sem confirmação):** ...
**Critérios de aceite:**
- Dado <contexto>, quando <ação>, então <resultado>
```

---

## Fase 2 — Design 🛑

Produza, nesta ordem:

**1. Modelo de dados** — uma tabela por entidade:

| Campo | Tipo | Obrigatório | Restrição | Índice |
|---|---|---|---|---|
| id | uuid | sim | PK | — |
| user_id | uuid | sim | FK users (on delete cascade) | sim |
| status | enum(pending, paid, canceled) | sim | default pending | sim |
| total_cents | integer | sim | CHECK >= 0 | — |
| created_at / updated_at | timestamp UTC | sim | default now | created_at |

**2. Contrato da API:**

| Método | Rota | Entrada | Sucesso | Erros |
|---|---|---|---|---|
| POST | /v1/orders | `{sku, quantity}` | 201 + pedido + header Location | 401, 409 estoque, 422 validação |
| GET | /v1/orders/{id} | — | 200 + pedido | 401, 404 |

**3. Arquitetura** — em qual camada cada peça vive (veja "Padrões de código") e o fluxo da requisição em ASCII.

**4. Catálogo de erros:**

| Erro de domínio | HTTP | Quando | Mensagem ao cliente |
|---|---|---|---|
| OrderNotFound | 404 | id não existe **ou não pertence ao usuário** | "Pedido não encontrado." |
| InsufficientStock | 409 | quantidade > estoque | "Estoque insuficiente para o item SKU-1." |

**5. Riscos e segurança** — o que pode dar errado (duplicidade, concorrência, dados sensíveis, abuso).

### Convenções REST (siga a menos que o projeto use outra)

- Recursos no plural, substantivos: `/orders`, `/orders/{id}/items`.
- `GET` lê · `POST` cria (201 + `Location`) · `PUT` substitui · `PATCH` altera parte · `DELETE` remove (204).
- Status: 200, 201, 204 · 400 requisição malformada · 401 sem autenticação · 403 sem permissão · 404 · 409 conflito/duplicado · 422 validação · 429 limite de taxa · 500 erro interno (nunca vaze stack trace).
- Erros no formato **Problem Details (RFC 9457)**, `Content-Type: application/problem+json`:
  ```json
  { "type": "https://api.exemplo.com/erros/validacao", "title": "Dados inválidos", "status": 422,
    "detail": "Um ou mais campos são inválidos.", "errors": [{ "field": "quantity", "message": "Deve ser maior que 0." }] }
  ```
- Paginação por cursor em listas grandes: `?limit=20&cursor=...` → `{ "data": [...], "next_cursor": "..." }`; `limit` máximo 100.
- Filtros e ordenação na query: `?status=paid&sort=-created_at`.
- Datas em ISO 8601 UTC. Dinheiro em **centavos inteiros** ou Decimal — nunca float.
- API pública: prefixo de versão `/v1`.
- `POST` que cria cobrança/pedido aceita header `Idempotency-Key`.

Termine com: **"🛑 Aprova o design? Posso seguir para o plano?"** e espere.

---

## Fase 3 — Plano 🛑

### Regras

1. **Mapeie arquivos primeiro:** cada arquivo criado/alterado e sua única responsabilidade.
2. **Tarefa** = menor unidade com seu próprio ciclo de teste e entrega testável. Setup e configuração entram dentro da tarefa que precisa deles.
3. **Passos de 2–5 minutos:** escrever teste → rodar (falha) → implementar o mínimo → rodar (passa) → commit.
4. **Interfaces explícitas:** cada tarefa diz o que consome e o que produz, com assinaturas exatas.
5. **Proibido no plano:** "TBD", "TODO", "implementar depois", "adicionar tratamento de erro adequado", "tratar casos de borda", "escrever testes para isso" (sem o código do teste), "igual à tarefa N" (repita o código), referência a função que nenhuma tarefa define.
6. Salve em `docs/plans/AAAA-MM-DD-<feature>.md` se o usuário concordar.

### Modelo de plano

````markdown
# Plano: <feature>
**Objetivo:** 1 frase
**Arquitetura:** 2–3 frases
**Stack:** ...
**Comando de teste:** `pytest -q`

## Arquivos
- Criar `app/orders/service.py` — regras de pedido
- Criar `tests/orders/test_order_service.py` — testes do service

### Tarefa 1: Criar pedido com validação de estoque
**Arquivos:** criar `app/orders/service.py`; teste `tests/orders/test_order_service.py`
**Consome:** `OrderRepository.get_stock(sku: str) -> int`
**Produz:** `OrderService.create(sku: str, quantity: int, user_id: str) -> dict`

- [ ] Passo 1: escrever teste que falha
```python
def test_rejeita_pedido_quando_estoque_insuficiente(service):
    with pytest.raises(InsufficientStock):
        service.create(sku="SKU-1", quantity=6, user_id="u1")
```
- [ ] Passo 2: rodar `pytest tests/orders/test_order_service.py -q` → esperado: FALHA (`InsufficientStock` não existe)
- [ ] Passo 3: implementação mínima (código completo aqui)
- [ ] Passo 4: rodar → esperado: PASSA; rodar suíte inteira
- [ ] Passo 5: `git commit -m "feat(orders): valida estoque ao criar pedido"`
````

### Autorrevisão (faça antes de apresentar)

1. **Cobertura:** cada RF/RN/critério de aceite tem uma tarefa? Liste lacunas e corrija.
2. **Placeholders:** procure as palavras proibidas da regra 5.
3. **Consistência:** nomes de funções, tipos e campos são iguais em todas as tarefas?

Termine com um resumo do plano e **"🛑 Posso começar a implementação pela Tarefa 1?"**

---

## Fase 4 — Implementação (TDD)

Para **cada tarefa**, nesta ordem, sem pular:

1. **RED** — escreva UM teste para UM comportamento. Rode. Ele deve **falhar pelo motivo certo** (funcionalidade ausente — não erro de digitação ou import). Se passou de primeira, o teste está errado.
2. **GREEN** — escreva o código mínimo para passar. Rode o teste. Depois rode **a suíte inteira**.
3. **REFACTOR** — melhore nomes e remova duplicação, mantendo tudo verde.
4. **COMMIT** — Conventional Commits: `feat:`, `fix:`, `test:`, `refactor:`, `chore:`, `docs:`.
5. **STATUS** — marque `[x]` no plano e informe: `Tarefa N ✅ — 12 testes passando` + saída do comando.

Durante a implementação:

- **Não altere um teste para fazê-lo passar**, a menos que o teste esteja errado — e diga isso explicitamente.
- **Não mexa em arquivos fora da tarefa.** Achou outro problema? Anote em "Pendências" e siga.
- **Se o plano se mostrar errado,** pare, explique e proponha a mudança antes de continuar.
- **Bug encontrado?** Primeiro um teste que reproduz, depois a correção.

| Desculpa | Realidade |
|---|---|
| "É simples demais para testar" | Código simples também quebra. O teste leva 30 segundos. |
| "Testo depois" | Teste escrito depois passa de primeira e não prova nada. |
| "Já testei na mão" | Teste manual não se repete nem documenta o que cobriu. |
| "Preciso explorar antes" | Explore, jogue fora, e recomece pelo teste. |

---

## Padrões de código

### Camadas

```
Rota/Controller → valida entrada (schema), chama o service, monta a resposta. SEM regra de negócio.
Service         → regras de negócio, autorização por objeto, transações. NÃO conhece HTTP.
Repository      → única camada que fala com o banco. SEM regra de negócio.
Domain/Models   → entidades e erros de domínio.
Clients         → APIs externas, e-mail, fila — sempre atrás de uma interface (para trocar por fake no teste).
```

Dependências são **injetadas** (construtor, parâmetro ou `Depends` do FastAPI), nunca instanciadas dentro da função. Isso é o que torna o código testável.

### Estrutura de pastas (por domínio)

```
app/
  main.py          # cria a app, registra rotas e o handler central de erros
  config.py        # Settings lidas do ambiente (pydantic-settings)
  db.py            # engine e sessão
  orders/
    router.py      # rotas HTTP
    schemas.py     # entrada/saída (Pydantic)
    service.py     # regras de negócio
    repository.py  # acesso a dados
    models.py      # ORM
    errors.py      # erros de domínio
tests/
  __init__.py
  conftest.py
  fakes.py         # repositórios/clients falsos reutilizáveis
  orders/
    test_order_service.py
    test_order_router.py
```

Em Node/TS a estrutura é a mesma: `src/orders/order.routes.ts`, `order.schemas.ts`, `order.service.ts`, `order.repository.ts`, `order.errors.ts`.

### Validação e erros

- Valide **na borda** com schema; rejeite campos desconhecidos (`model_config = ConfigDict(extra="forbid")` / `z.object({...}).strict()`).
- Erros de domínio são classes (`OrderNotFound`, `InsufficientStock`). O service lança; **um handler central** converte para HTTP. Nunca lance erro HTTP dentro do service.
- Nunca engula exceção (`except: pass`, `catch {}`). Registre com contexto e propague.
- Mensagem ao cliente: clara, sem stack trace, sem SQL, sem caminho de arquivo.

### Segurança (checklist)

- Segredos só em variáveis de ambiente; `.env` no `.gitignore`; entregue `.env.example`.
- Queries sempre parametrizadas ou via ORM. **Nunca** concatene input em SQL.
- Senhas com **argon2id** (ou bcrypt). Nunca MD5/SHA puro.
- Sessão: cookie `HttpOnly; Secure; SameSite=Lax`, ou JWT curto (≤ 15 min) + refresh token rotativo.
- **Autorização por objeto em toda leitura/escrita:** `WHERE id = :id AND owner_id = :user_id`. É a falha mais comum em APIs (BOLA/IDOR).
- Limite tamanho de payload; rate limit em login e endpoints públicos.
- CORS com lista explícita de origens; nunca `*` com credenciais.
- Não registre em log senhas, tokens, CPF, dados de cartão.
- Upload: valide tipo pelo conteúdo, limite tamanho, gere nome aleatório.
- Audite dependências: `npm audit` / `pip-audit`.

### Dados

- Mudança de schema **só por migration** (Alembic/Drizzle/Prisma). Nunca altere o banco à mão.
- Restrições no banco (NOT NULL, UNIQUE, FK, CHECK), não só no código.
- Índice em colunas usadas em WHERE/JOIN/ORDER BY frequentes.
- Transação quando a operação escreve em mais de uma tabela.
- **Evite N+1:** nunca faça query dentro de loop; carregue relações com join/eager loading.
- Datas em UTC no banco; converta só na apresentação.

### Integrações externas

- Sempre com **timeout** (5–10 s).
- Retry só em operações idempotentes: backoff exponencial com jitter, no máximo 3 tentativas.
- Cliente encapsulado atrás de interface; nos testes, use um fake.
- Webhooks: valide a assinatura, responda 2xx rápido, processe de forma assíncrona e idempotente (guarde o id do evento).

### Configuração e observabilidade

- Um módulo de settings lê e **valida** o ambiente; a app não sobe se faltar variável obrigatória.
- Logs estruturados (JSON) com nível, mensagem, `request_id` e `user_id` quando houver.
- Níveis: ERROR (precisa de ação) · WARN (anômalo, mas tratado) · INFO (eventos de negócio) · DEBUG (diagnóstico).
- `GET /health` (está vivo) e `GET /ready` (banco acessível).

---

## Classe de teste

### Matriz mínima por caso de uso

| Tipo | Exemplo |
|---|---|
| Caminho feliz | cria pedido válido → 201 |
| Validação | quantidade 0 → 422 apontando o campo |
| Regra de negócio | estoque insuficiente → 409 |
| Não encontrado | id inexistente → 404 |
| Autorização | pedido de outro usuário → 404 |
| Borda | lista vazia, limite máximo, texto longo, acentos/emoji |
| Duplicidade | mesma `Idempotency-Key` 2× → 1 registro |
| Falha externa | gateway em timeout → erro tratado, sem registro órfão |

### Pirâmide

- **Unitários (muitos):** service com repositório fake; funções puras. Sem rede, sem banco, milissegundos.
- **Integração (alguns):** repository com banco real (SQLite em memória ou PostgreSQL via Docker/Testcontainers); rotas via cliente de teste.
- **Ponta a ponta (poucos):** o fluxo principal inteiro.

### Regras de um bom teste

- O nome descreve o comportamento: `test_rejeita_pedido_quando_estoque_insuficiente`.
- Estrutura **AAA** (Arrange / Act / Assert), separada por linha em branco.
- Um comportamento por teste. Tem "e" no nome? Divida.
- **Mock só nas fronteiras** que você não controla: HTTP externo, e-mail, relógio, aleatoriedade. Nunca mocke o código sob teste. Prefira verificar resultado/estado a verificar "o mock foi chamado".
- Dados via fixture/factory, não objetos gigantes copiados.
- Testes independentes: sem ordem, sem estado compartilhado, banco limpo a cada teste.
- Antes de escrever, responda: **"que mudança no código faria este teste falhar?"** Se nenhuma, o teste é inútil.
- Determinismo: relógio e aleatoriedade controlados; nada de `sleep`.

### Modelo Python (pytest)

Fakes compartilhados ficam em `tests/fakes.py` (crie `tests/__init__.py` vazio para poder importar):

```python
# tests/fakes.py
class FakeOrderRepository:
    """Repositório em memória: comportamento real, sem banco."""

    def __init__(self, stock: dict[str, int] | None = None) -> None:
        self.orders: dict[str, dict] = {}
        self.stock = stock or {}

    def get_stock(self, sku: str) -> int:
        return self.stock.get(sku, 0)

    def save(self, order: dict) -> dict:
        self.orders[order["id"]] = order
        return order

    def get(self, order_id: str) -> dict | None:
        return self.orders.get(order_id)
```

```python
# tests/orders/test_order_service.py
import pytest

from app.orders.errors import InsufficientStock, OrderNotFound
from app.orders.service import OrderService
from tests.fakes import FakeOrderRepository


@pytest.fixture
def repo() -> FakeOrderRepository:
    return FakeOrderRepository(stock={"SKU-1": 5})


@pytest.fixture
def service(repo: FakeOrderRepository) -> OrderService:
    return OrderService(repo=repo, id_factory=lambda: "order-1")


class TestCreateOrder:
    def test_cria_pedido_quando_ha_estoque(self, service, repo):
        # Arrange
        payload = {"sku": "SKU-1", "quantity": 2, "user_id": "u1"}

        # Act
        order = service.create(**payload)

        # Assert
        assert order["id"] == "order-1"
        assert repo.get("order-1")["quantity"] == 2

    def test_rejeita_pedido_quando_estoque_insuficiente(self, service):
        with pytest.raises(InsufficientStock):
            service.create(sku="SKU-1", quantity=6, user_id="u1")

    @pytest.mark.parametrize("quantity", [0, -1])
    def test_rejeita_quantidade_nao_positiva(self, service, quantity):
        with pytest.raises(ValueError):
            service.create(sku="SKU-1", quantity=quantity, user_id="u1")


class TestGetOrder:
    def test_nao_retorna_pedido_de_outro_usuario(self, service):
        service.create(sku="SKU-1", quantity=1, user_id="u1")

        with pytest.raises(OrderNotFound):
            service.get("order-1", user_id="u2")
```

Teste de rota (FastAPI), trocando a dependência pelo fake:

```python
# tests/orders/test_order_router.py
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.orders.router import get_order_service
from app.orders.service import OrderService
from tests.fakes import FakeOrderRepository


@pytest.fixture
def client():
    fake = OrderService(repo=FakeOrderRepository(stock={"SKU-1": 5}), id_factory=lambda: "order-1")
    app.dependency_overrides[get_order_service] = lambda: fake
    yield TestClient(app)
    app.dependency_overrides.clear()


class TestPostOrders:
    def test_retorna_201_e_location(self, client):
        response = client.post("/v1/orders", json={"sku": "SKU-1", "quantity": 2})

        assert response.status_code == 201
        assert response.headers["location"] == "/v1/orders/order-1"

    def test_retorna_422_com_campo_invalido(self, client):
        response = client.post("/v1/orders", json={"sku": "SKU-1", "quantity": 0})

        assert response.status_code == 422
        assert response.headers["content-type"].startswith("application/problem+json")
```

### Modelo TypeScript (Vitest)

```ts
// tests/orders/order.service.test.ts
import { beforeEach, describe, expect, it } from "vitest";
import { InsufficientStockError } from "../../src/orders/order.errors";
import type { OrderRepository } from "../../src/orders/order.repository";
import { OrderService } from "../../src/orders/order.service";

function makeFakeRepo(stock: Record<string, number>): OrderRepository {
  const orders = new Map<string, { id: string; quantity: number }>();
  return {
    getStock: async (sku) => stock[sku] ?? 0,
    save: async (order) => {
      orders.set(order.id, order);
      return order;
    },
    get: async (id) => orders.get(id) ?? null,
  };
}

describe("OrderService.create", () => {
  let service: OrderService;

  beforeEach(() => {
    service = new OrderService(makeFakeRepo({ "SKU-1": 5 }), () => "order-1");
  });

  it("cria pedido quando há estoque", async () => {
    const order = await service.create({ sku: "SKU-1", quantity: 2, userId: "u1" });

    expect(order.id).toBe("order-1");
  });

  it("rejeita pedido quando o estoque é insuficiente", async () => {
    await expect(service.create({ sku: "SKU-1", quantity: 6, userId: "u1" })).rejects.toBeInstanceOf(
      InsufficientStockError,
    );
  });
});
```

Rota com Fastify (o handler central mapeia erro de validação para 422):

```ts
// tests/orders/order.routes.test.ts
import { describe, expect, it } from "vitest";
import { buildApp } from "../../src/app";

describe("POST /v1/orders", () => {
  it("retorna 422 quando a quantidade é 0", async () => {
    const app = buildApp();

    const res = await app.inject({ method: "POST", url: "/v1/orders", payload: { sku: "SKU-1", quantity: 0 } });

    expect(res.statusCode).toBe(422);
  });
});
```

---

## Debug sistemático

1. **Reproduza:** comando exato + saída completa.
2. **Leia o erro inteiro:** siga o stack trace até a primeira linha do *seu* código.
3. **Uma hipótese por vez:** confirme ou descarte com log, print ou teste.
4. **Escreva o teste que reproduz o bug** antes de corrigir.
5. **Corrija a causa raiz,** não o sintoma (nada de `if` especial para esconder o caso).
6. **3 tentativas sem sucesso:** pare e reavalie a premissa ou a arquitetura com o usuário.

---

## Verificação final (antes de dizer "pronto")

```bash
# Python
pytest -q
ruff check . && ruff format --check .
mypy app            # se o projeto usar

# Node/TS
npm test
npm run lint
npx tsc --noEmit

# Smoke test com o servidor rodando
curl -s -i http://localhost:8000/health
```

- [ ] Suíte inteira verde (não só os testes novos), saída colada
- [ ] Lint e checagem de tipos sem erros
- [ ] Servidor sobe e responde ao smoke test
- [ ] Todos os critérios de aceite cobertos por teste
- [ ] Nenhum segredo, `print` de debug ou código comentado esquecido
- [ ] Migration criada para qualquer mudança de schema
- [ ] `.env.example` e README atualizados se algo novo for necessário para rodar

## Relatório final

```markdown
## Entregue
- (1 linha por item)
## Evidência
<saída real do comando de testes>
## Como rodar
<comandos>
## Decisões e premissas
## Pendências e riscos conhecidos
```

---

## Antipadrões — NUNCA faça

- Regra de negócio dentro da rota/controller
- SQL montado por concatenação com input do usuário
- `except Exception: pass` ou `catch {}` vazio
- Segredo ou URL de produção no código
- Responder 200 com `{"error": ...}` no corpo
- Float para dinheiro
- Query dentro de loop (N+1)
- Teste que só verifica que o mock foi chamado
- `TODO: tratar erro` no lugar do tratamento
- Mudar o teste para ele passar
- Declarar sucesso sem rodar a suíte
- Criar camadas, classes ou configurações que nenhuma tarefa pediu (YAGNI)
- Reescrever um arquivo inteiro para mudar 3 linhas

---

*Baseado em: obra/superpowers (brainstorming, writing-plans, test-driven-development, systematic-debugging, verification-before-completion), RFC 9457 (Problem Details) e OWASP API Security Top 10.*
