---
name: frontend-ui
description: Fluxo para criar ou redesenhar interfaces web modernas — páginas, landing pages, dashboards, apps, formulários e componentes — com UI/UX atual. Cobre levantamento, direção visual, tokens de design (cor OKLCH, tipografia fluida, espaçamento, movimento), plano de telas e estados, implementação com HTML/CSS/JS modernos ou React, acessibilidade WCAG 2.2, performance (Core Web Vitals), revisão visual e testes. Use SEMPRE que a tarefa envolver qualquer coisa visual no navegador — tela, layout, estilo, CSS, componente, "deixar bonito", "modernizar", "melhorar o visual", "está feio/antigo" — mesmo que o usuário não diga "frontend". Para cenas 3D, Three.js ou jogos use a skill game-3d (esta continua valendo para menus e HUD).
---

# Frontend UI

Você atua como **designer de produto + engenheiro frontend sênior**. Você tem dois inimigos:

- **Visual antiquado:** cara de Bootstrap 2015, sombras pretas pesadas, gradiente em botão, tudo centralizado dentro de caixas, texto pequeno.
- **Visual genérico de IA:** gradiente roxo, Inter em tudo, cards idênticos, enfeites sem motivo.

Toda escolha visual precisa de um **motivo ligado ao assunto do projeto**. Se você não sabe explicar por que escolheu uma cor ou fonte, a escolha é genérica.

## 0. Regras de ouro

1. **Leia antes de escrever:** `package.json`, CSS global, componentes existentes. Em projeto existente, melhore **dentro** do sistema de design que já existe.
2. **Decida o visual antes de codar** (Fase 2). Código sem direção vira visual genérico.
3. **Tokens primeiro:** nenhuma cor, tamanho, espaçamento, raio ou duração "solto" no código. Tudo vem de variáveis CSS.
4. **Todo componente tem todos os estados:** padrão, hover, foco, ativo, desabilitado, carregando, vazio, erro, sucesso.
5. **Mobile-first e acessível desde o início** — não é etapa opcional no fim.
6. **Conteúdo real:** nada de "Lorem ipsum". Escreva textos plausíveis para o assunto.
7. **Não invente APIs:** confira a versão das bibliotecas no projeto antes de usar um recurso.
8. **Evidência:** só diga "pronto" depois de rodar build/testes e, se possível, ver um screenshot.
9. **Pare nos portões 🛑** e espere aprovação.
10. **Ao editar,** escreva o bloco completo; nunca "... resto igual ..." em código que será salvo.

## Mapa do fluxo

```
Levantamento → Direção visual + tokens 🛑 → Plano de telas e componentes 🛑 → Implementação → Revisão → Testes → Relatório
```

Ajuste pequeno (um componente, um bug visual): pule os portões, mas respeite tokens, estados e acessibilidade. Sempre anuncie a fase: `**Fase 2 — Direção visual**`.

---

## Fase 1 — Levantamento

### 1.1 Reconheça o projeto

```bash
cat package.json 2>/dev/null
ls src 2>/dev/null; ls src/components 2>/dev/null
find . -path ./node_modules -prune -o \( -name "*.css" -o -name "tailwind.config.*" -o -name "tokens*" \) -print | head -20
```

Anote: framework, se usa Tailwind/CSS Modules/CSS puro, biblioteca de componentes, tokens ou variáveis existentes, fontes, ícones.

### 1.2 Stack padrão (projeto novo, se o usuário não definir)

| Caso | Use |
|---|---|
| Página/landing simples | HTML + CSS + JS (ES modules), sem build |
| App com estado/rotas | Vite + React + TypeScript |
| Estilo | CSS puro com tokens (ou CSS Modules). Tailwind v4 só se o usuário quiser ou já usar |
| Ícones | Lucide (`lucide` ou `lucide-react`) — nunca emoji como ícone |
| Fontes | Google Fonts ou Fontsource, no máximo 2 famílias |
| Componentes acessíveis (React) | Radix UI / shadcn/ui como **base de comportamento** — troque os tokens; o visual padrão deles não é uma direção |

Criar projeto: `npm create vite@latest meu-app -- --template react-ts`

### 1.3 Perguntas (até 3, cada uma com um padrão)

- Para quem é e qual a **ação principal** que a pessoa precisa fazer nesta tela?
- Qual o assunto/marca e que sensação deve passar (confiável, divertido, técnico, luxuoso…)?
- Tem referências que gosta ou odeia? Tema claro, escuro ou ambos?

### 1.4 Saída obrigatória

```markdown
## Brief
**Assunto:** ...            **Público:** ...
**Tarefa principal do usuário:** ...
**Tom:** ...                **Tema:** claro / escuro / ambos
**Telas:** ...
**Restrições:** marca, stack, prazo, conteúdo existente
```

---

## Fase 2 — Direção visual + tokens 🛑

### 2.1 Ancore no assunto

Liste **5 coisas concretas do mundo do assunto** (materiais, objetos, lugares, vocabulário, cores reais). É daí que saem as escolhas. Exemplo — app de padaria artesanal: farinha, papel kraft, forno a lenha, quadro de giz, casca dourada do pão.

### 2.2 Escolha UMA direção de partida e adapte

| Direção | Bom para | Tipografia (títulos / texto) | Cor | Forma | Movimento |
|---|---|---|---|---|---|
| **Precisão** | dashboards, ferramentas, B2B | Geist / Geist (números tabulares) | neutros frios + 1 acento saturado | raio 6–8px, bordas 1px, densidade média | rápido (120–180ms), funcional |
| **Editorial** | blog, portfólio, institucional | Fraunces ou Newsreader / Source Serif 4 ou Instrument Sans | papel claro frio + tinta escura + 1 acento profundo | raio 0–4px, grid assimétrico, muito respiro | fades sutis |
| **Acolhedor** | saúde, educação, consumo, comunidade | Bricolage Grotesque / Figtree | superfícies claras no matiz da marca + acento quente | raio 14–20px, formas orgânicas | suave (200–300ms) |
| **Expressivo** | eventos, música, marcas jovens | Archivo expandido ou Unbounded / Archivo | duotone saturado, alto contraste | tipografia enorme, blocos de cor chapada, raio 0 ou pílula | 1 transição marcante |
| **Imersivo escuro** | mídia, criativo, premium, produto 3D | Instrument Serif / Instrument Sans | fundo escuro com matiz (nunca #000) + 1 acento luminoso | raio 10–12px, camadas, profundidade | lento e suave (300–500ms) |
| **Lúdico** | jogos, hobby, infantil | Chakra Petch ou Rubik / Rubik | cores vivas sobre neutro | bordas grossas, sombra sólida deslocada | elástico e curto |

Depois de escolher, **adapte** obrigatoriamente:
1. Mude o matiz do acento para algo que venha do assunto (2.1).
2. Defina **um elemento-assinatura** — a única coisa memorável da interface (um tratamento tipográfico, uma forma, uma textura, uma interação). Todo o resto fica calmo.
3. Escreva 3 princípios da interface em uma linha cada.

### 2.3 Sinais de "feito por IA" — evite, a menos que o brief peça

- Gradiente roxo/azul sobre branco; Inter, Roboto ou Arial em tudo
- Fundo creme + serifa de alto contraste + acento terracota
- Fundo quase preto + um único acento verde-ácido ou vermelhão
- Kit SaaS: tudo em cards arredondados iguais, mesmo raio em tudo, mesma sombra cinza, manchas de gradiente decorativo
- Rótulo em CAIXA ALTA espaçada acima de todo título; textos "A · B · C"; "→" em todo botão; uma palavra do título em outra cor/itálico
- Numeração 01 / 02 / 03 em conteúdo que não é sequência
- Hero = número gigante + rótulo pequeno + gradiente
- Fade-and-slide-up em cada seção; todo card "levanta" no hover
- Glassmorphism em tudo; emoji como ícone

### 2.4 Sinais de "antiquado" — evite sempre

- Azul `#007bff`, botões com gradiente ou relevo, sombras pretas pesadas
- Corpo de texto < 16px, linhas com mais de 80 caracteres, pouco espaço entre blocos
- Tudo centralizado numa coluna estreita de caixas; tabela usada como layout; carrossel no topo
- Cores puras (`#FF0000`, `#00FF00`), bordas cinza grossas em tudo
- `alert()` / `confirm()` nativos; links azuis sublinhados sem tratamento; Times/Arial padrão
- Ícones em PNG/JPG, imagens esticadas, `px` fixo sem responsividade
- Animação de `top/left` via JS; `transition: all`; jQuery

### 2.5 Regras dos tokens

- **Cor em OKLCH.** Neutros levemente tingidos com o matiz da marca (croma 0.004–0.02). Um acento de ação + cores semânticas (sucesso, alerta, perigo). Proporção ~60% neutro / 30% superfícies secundárias / 10% acento.
- **Contraste (WCAG 2.2 AA):** texto normal ≥ 4.5:1; texto grande (≥ 24px, ou ≥ 18.66px bold) e ícones/bordas de controle ≥ 3:1.
- **Tema escuro não é inversão:** superfícies mais elevadas ficam mais claras; acento um pouco mais claro e menos saturado; texto ~94% de luminosidade (não branco puro); sombras quase invisíveis — use bordas e superfícies para dar elevação.
- **Tipografia:** escala de razão 1.2–1.333, fluida com `clamp()`. Corpo 16–18px, entrelinha 1.5–1.7. Títulos com entrelinha 1.05–1.2 e espaçamento levemente negativo. Linha de leitura 60–75 caracteres. Números em tabelas: `tabular-nums`.
- **Espaço:** base 4px (4, 8, 12, 16, 24, 32, 48, 64, 96, 128). Espaço menor *dentro* de um grupo, maior *entre* grupos.
- **Raio com hierarquia:** controles pequenos < cartões < painéis. Raio interno = raio externo − padding.
- **Movimento:** 120ms (micro), 200ms (padrão), 320ms (painéis), 500ms (momento orquestrado). Saída mais rápida que entrada.

### 2.6 Modelo `tokens.css` (copie e ajuste os VALORES; não renomeie as variáveis)

```css
:root {
  color-scheme: light dark; /* segue o sistema; [data-theme] força um tema */

  /* Matizes 0–360: trocar estes dois recolore a interface inteira */
  --hue: 255;        /* tinta dos neutros */
  --accent-hue: 160; /* cor de ação, tirada do assunto */

  /* Cores: light-dark(<claro>, <escuro>) */
  --bg:           light-dark(oklch(98.5% 0.004 var(--hue)), oklch(17% 0.012 var(--hue)));
  --surface:      light-dark(oklch(100% 0 0),               oklch(21% 0.014 var(--hue)));
  --surface-2:    light-dark(oklch(96% 0.006 var(--hue)),   oklch(25% 0.016 var(--hue)));
  --border:       light-dark(oklch(89% 0.010 var(--hue)),   oklch(33% 0.018 var(--hue))); /* divisores, cartões */
  --border-strong:light-dark(oklch(62% 0.020 var(--hue)),   oklch(55% 0.020 var(--hue))); /* bordas de inputs: 3:1 */
  --text:         light-dark(oklch(22% 0.020 var(--hue)),   oklch(94% 0.008 var(--hue)));
  --text-muted:   light-dark(oklch(45% 0.020 var(--hue)),   oklch(72% 0.014 var(--hue)));

  --accent:       light-dark(oklch(50% 0.13 var(--accent-hue)), oklch(76% 0.12 var(--accent-hue)));
  --accent-hover: light-dark(oklch(44% 0.13 var(--accent-hue)), oklch(82% 0.11 var(--accent-hue)));
  --on-accent:    light-dark(oklch(99% 0.01 var(--accent-hue)), oklch(18% 0.03 var(--accent-hue)));
  --accent-soft:  light-dark(oklch(94% 0.04 var(--accent-hue)), oklch(30% 0.05 var(--accent-hue)));

  --success: light-dark(oklch(48% 0.12 150), oklch(78% 0.13 150));
  --warning: light-dark(oklch(52% 0.12 70),  oklch(84% 0.13 80));
  --danger:  light-dark(oklch(50% 0.18 27),  oklch(74% 0.15 25));

  --shadow-color: light-dark(oklch(25% 0.03 var(--hue) / 0.12), oklch(5% 0 0 / 0.5));
  --shadow-1: 0 1px 2px var(--shadow-color);
  --shadow-2: 0 2px 4px -2px var(--shadow-color), 0 6px 16px -4px var(--shadow-color);
  --shadow-3: 0 4px 10px -4px var(--shadow-color), 0 18px 40px -8px var(--shadow-color);

  /* Tipografia (troque as famílias pela direção escolhida) */
  --font-display: "Fraunces", Georgia, serif;
  --font-body: "Instrument Sans", system-ui, sans-serif;
  --font-mono: ui-monospace, "SFMono-Regular", Menlo, Consolas, monospace;

  --step--1: clamp(0.83rem, 0.80rem + 0.15vw, 0.90rem);
  --step-0:  clamp(1.00rem, 0.96rem + 0.20vw, 1.125rem);
  --step-1:  clamp(1.20rem, 1.12rem + 0.40vw, 1.40rem);
  --step-2:  clamp(1.44rem, 1.30rem + 0.70vw, 1.75rem);
  --step-3:  clamp(1.73rem, 1.50rem + 1.15vw, 2.20rem);
  --step-4:  clamp(2.07rem, 1.70rem + 1.90vw, 2.90rem);
  --step-5:  clamp(2.49rem, 1.90rem + 3.00vw, 4.00rem);

  /* Espaço (base 4px) */
  --space-1: 0.25rem; --space-2: 0.5rem; --space-3: 0.75rem; --space-4: 1rem;  --space-5: 1.5rem;
  --space-6: 2rem;    --space-7: 3rem;   --space-8: 4rem;    --space-9: 6rem;  --space-10: 8rem;

  /* Forma */
  --radius-sm: 6px; --radius-md: 10px; --radius-lg: 16px; --radius-pill: 999px;

  /* Movimento */
  --dur-1: 120ms; --dur-2: 200ms; --dur-3: 320ms; --dur-4: 500ms;
  --ease-out: cubic-bezier(0.2, 0, 0, 1);
  --ease-in-out: cubic-bezier(0.4, 0, 0.2, 1);

  /* Layout */
  --container: 72rem;
  --measure: 68ch;
}

:root[data-theme="light"] { color-scheme: light; }
:root[data-theme="dark"]  { color-scheme: dark; }
```

Com Tailwind v4, exponha os tokens assim (no CSS principal): `@theme inline { --color-bg: var(--bg); --color-accent: var(--accent); --font-display: var(--font-display); }`.

### 2.7 Saída obrigatória

```markdown
## Direção visual
**5 elementos do assunto:** ...
**Direção:** <nome> adaptada — por quê
**Elemento-assinatura:** ...
**Princípios:** 1) ... 2) ... 3) ...
**Paleta:** 4–6 cores nomeadas (OKLCH)   **Tipografia:** famílias e papéis
**Layout:** conceito em 1 frase + wireframe ASCII da tela principal (mobile e desktop)
**Revisão anti-genérico:** o que eu mudei por parecer padrão de IA ou antiquado
```

Termine com **"🛑 Aprova a direção visual?"** e espere.

---

## Fase 3 — Plano de telas e componentes 🛑

1. **Arquitetura de informação:** para cada tela — objetivo, **uma** ação principal, conteúdo em ordem de prioridade.
2. **Wireframe ASCII** de cada tela em 390px e 1440px.
3. **Inventário de componentes:**

| Componente | Variações | Estados | Onde aparece |
|---|---|---|---|
| Button | primary, secondary, ghost, danger; sm/md/lg | default, hover, focus, active, disabled, loading | todas |

4. **Estados de dados** para cada conteúdo assíncrono: carregando (skeleton se > 300ms), vazio (explica + convida a agir), erro (o que houve + como resolver + "Tentar novamente"), sucesso.
5. **Lista de tarefas** com os arquivos de cada uma.

Termine com **"🛑 Posso implementar?"** e espere.

---

## Fase 4 — Implementação

**Ordem:** `tokens.css` + `base.css` → esqueleto semântico do layout → componentes com todos os estados → conteúdo real → interações → responsividade → polimento.

### 4.1 Base CSS (copie)

```css
@layer reset, base, components, utilities;

@layer reset {
  *, *::before, *::after { box-sizing: border-box; }
  * { margin: 0; }
  html { -webkit-text-size-adjust: 100%; text-size-adjust: 100%; scroll-padding-top: var(--space-8); }
  body { min-height: 100dvh; line-height: 1.6; -webkit-font-smoothing: antialiased; }
  img, picture, video, canvas, svg { display: block; max-width: 100%; height: auto; }
  input, button, textarea, select { font: inherit; color: inherit; }
  p, li, h1, h2, h3, h4 { overflow-wrap: break-word; }
}

@layer base {
  body { background: var(--bg); color: var(--text); font-family: var(--font-body); font-size: var(--step-0); }
  h1, h2, h3 { font-family: var(--font-display); line-height: 1.12; letter-spacing: -0.015em; text-wrap: balance; }
  h1 { font-size: var(--step-5); }
  h2 { font-size: var(--step-4); }
  h3 { font-size: var(--step-2); }
  p  { max-width: var(--measure); text-wrap: pretty; }
  a  { color: var(--accent); text-underline-offset: 0.2em; }
  a:hover { color: var(--accent-hover); }
  :focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
  ::selection { background: var(--accent-soft); }
  .tabular { font-variant-numeric: tabular-nums; }
  .container { width: min(100% - 2 * var(--space-4), var(--container)); margin-inline: auto; }
}

@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: 0.01ms !important; animation-iteration-count: 1 !important;
    transition-duration: 0.01ms !important; scroll-behavior: auto !important;
  }
}
```

### 4.2 Componente com todos os estados (padrão a seguir)

```css
@layer components {
  .btn {
    display: inline-flex; align-items: center; justify-content: center; gap: var(--space-2);
    min-height: 44px; padding: 0 var(--space-5);
    border: 1px solid transparent; border-radius: var(--radius-sm);
    font-weight: 600; cursor: pointer; touch-action: manipulation;
    transition: background-color var(--dur-1) var(--ease-out), border-color var(--dur-1) var(--ease-out),
                transform var(--dur-1) var(--ease-out);
  }
  .btn-primary { background: var(--accent); color: var(--on-accent); }
  .btn-primary:hover { background: var(--accent-hover); }
  .btn-secondary { background: var(--surface); border-color: var(--border); color: var(--text); }
  .btn-secondary:hover { background: var(--surface-2); }
  .btn-danger { background: var(--danger); color: var(--on-accent); } /* on-accent já é claro/escuro por tema */
  .btn:active { transform: translateY(1px); }
  .btn:disabled, .btn[aria-disabled="true"] { opacity: 0.5; cursor: not-allowed; }
  .btn[aria-busy="true"] { cursor: progress; }
}
```

Campo de formulário acessível:

```html
<div class="field">
  <label for="email">E-mail</label>
  <input id="email" name="email" type="email" autocomplete="email" required
         aria-describedby="email-hint email-error">
  <p id="email-hint" class="hint">Enviaremos o recibo para este endereço.</p>
  <p id="email-error" class="error" aria-live="polite"></p>
</div>
```

```css
.field { display: grid; gap: var(--space-2); }
.field input { min-height: 44px; padding: 0 var(--space-3); border: 1px solid var(--border-strong);
               border-radius: var(--radius-sm); background: var(--surface); }
.field:has(input[aria-invalid="true"]) input { border-color: var(--danger); }
.field .error { color: var(--danger); font-size: var(--step--1); }
.field .error:empty { display: none; }
```

Modal nativo (foco preso e Esc de graça) com animação de entrada:

```html
<dialog id="confirm-delete" aria-labelledby="confirm-delete-title">
  <form method="dialog">
    <h2 id="confirm-delete-title">Excluir projeto?</h2>
    <p>Os 12 arquivos deste projeto serão removidos permanentemente.</p>
    <div class="actions">
      <button class="btn btn-secondary" value="cancel">Cancelar</button>
      <button class="btn btn-danger" value="confirm">Excluir projeto</button>
    </div>
  </form>
</dialog>
```

```css
dialog { border: 0; border-radius: var(--radius-lg); padding: var(--space-6); background: var(--surface);
         color: var(--text); box-shadow: var(--shadow-3); opacity: 0; translate: 0 8px;
         transition: opacity var(--dur-2) var(--ease-out), translate var(--dur-2) var(--ease-out),
                     overlay var(--dur-2) allow-discrete, display var(--dur-2) allow-discrete; }
dialog[open] { opacity: 1; translate: 0 0; }
@starting-style { dialog[open] { opacity: 0; translate: 0 8px; } }
dialog::backdrop { background: oklch(15% 0.02 var(--hue) / 0.5); }
```

### 4.3 HTML semântico

- `header`, `nav`, `main` (um só), `section` com título, `article`, `aside`, `footer`.
- Um `h1` por página; níveis de título sem pular.
- `<button>` para ações, `<a href>` para navegação. Nunca `div` clicável.
- Todo input com `<label>`; listas com `ul`/`ol`; tabela só para dados tabulares.
- Link "Pular para o conteúdo" como primeiro elemento focável.
- `<html lang="pt-BR">` e `<meta name="theme-color">` igual ao fundo.

### 4.4 CSS moderno — use

- **Grid** para o layout da página; **flex** para alinhar dentro de componentes; `gap` em vez de margens entre irmãos.
- Grade responsiva sem media query: `grid-template-columns: repeat(auto-fit, minmax(min(100%, 18rem), 1fr));`
- **Container queries** para componentes que mudam conforme o espaço: `container-type: inline-size;` + `@container (min-width: 30rem) { ... }`.
- `clamp()`, `min()`, `max()` para tamanhos fluidos; unidades `dvh`/`svh` para altura em mobile.
- `:has()` para estado do pai, `:focus-visible`, `:where()` para baixar especificidade.
- Aninhamento nativo e `@layer` para controlar a cascata.
- `color-mix()` para cores derivadas; `light-dark()` para temas.
- `<dialog>` para modais, atributo `popover` para menus/tooltips, `@starting-style` para animar entrada.
- View Transitions para trocas de estado/página: `if (document.startViewTransition) document.startViewTransition(update); else update();`
- Melhoria progressiva (use com `@supports` e alternativa): anchor positioning, animações dirigidas por scroll.

### 4.5 JavaScript

- ES modules; sem jQuery; delegação de eventos; nada de `onclick` inline.
- Nunca `innerHTML` com dado do usuário (XSS) — use `textContent` ou o framework.
- `fetch` com `AbortController` e timeout; trate erro de rede e status ≠ 2xx.
- Datas e números com `Intl` (`new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" })`).
- Estado da interface relevante (filtro, aba, página) refletido na URL.

### 4.6 React (se o projeto usar)

- Componentes pequenos, props tipadas, um arquivo por componente.
- Estado o mais perto possível de onde é usado; valor derivado é **calculado**, não guardado em `useState`.
- `useEffect` só para sincronizar com algo externo (rede, DOM, timers) — com limpeza.
- `key` estável (id, nunca índice em listas que mudam).
- Listas com mais de ~100 itens: virtualize. Rotas: `lazy()` + `Suspense`.
- Dados do servidor: TanStack Query (ou o padrão do projeto), com estados de loading/erro tratados na UI.

---

## Princípios de UX (aplique em toda tela)

- **Hierarquia:** uma ação principal por tela (um botão primário). Secundárias visualmente mais fracas.
- **Lei de Hick:** menos opções visíveis; esconda o avançado atrás de divulgação progressiva.
- **Lei de Fitts:** alvos de toque ≥ 44×44px (mínimo WCAG 24×24); ações frequentes ao alcance do polegar no mobile.
- **Lei de Jakob:** use padrões conhecidos (logo leva à home, busca no topo, perfil no canto superior direito).
- **Gestalt:** proximidade agrupa; elementos iguais parecem iguais; alinhe tudo a uma grade.
- **Feedback:** toda ação responde visualmente em < 100ms; operações > 1s mostram progresso; prefira **desfazer** a pedir confirmação; confirmação só para destrutivo irreversível.
- **Prevenção de erro:** valide ao sair do campo, mostre exemplo de formato, nunca apague o que a pessoa digitou.
- **Reconhecer > lembrar:** rótulos sempre visíveis (placeholder não é rótulo), item ativo da navegação destacado (`aria-current="page"`), filtros aplicados visíveis.
- **Consistência:** a mesma ação tem o mesmo nome no fluxo inteiro ("Publicar" → aviso "Publicado").
- **Texto da interface:** voz ativa; botões com verbo específico ("Salvar alterações", não "Enviar"); erro diz o que houve e como resolver, sem pedir desculpas e sem culpar o usuário; estado vazio convida à ação.

### Movimento

- Movimento tem função: **feedback** (respondeu ao clique), **orientação** (de onde veio, para onde foi), **continuidade** (o mesmo objeto mudou de estado).
- No máximo **um momento orquestrado** por página (ex.: entrada do topo). Nada de animação em cada seção.
- Anime só `transform` e `opacity`. Nunca `transition: all` — liste as propriedades.
- Respeite `prefers-reduced-motion` (já está no base.css).

### Padrões de componentes

| Componente | Regras |
|---|---|
| Botão | alturas 36/44/52px; ícone + texto alinhados; estado de carregando mantém a largura |
| Input | rótulo acima; altura ≥ 44px; `type`, `inputmode` e `autocomplete` corretos; erro com ícone + texto ligado por `aria-describedby` |
| Formulário | uma coluna; campos relacionados agrupados; botão principal no fim, alinhado aos campos |
| Card | só quando o conteúdo é uma unidade clicável/independente; não transforme a página toda em cards |
| Navegação | ≤ 7 itens no topo; página atual marcada; no mobile, menu com botão `aria-expanded` |
| Modal | `<dialog>`; título; botão fechar; Esc fecha; foco volta ao gatilho |
| Toast | `aria-live="polite"`; some após ≥ 5s; nunca para erro crítico |
| Tabela | cabeçalho fixo; números à direita com `tabular-nums`; no mobile, rolagem horizontal dentro do contêiner ou vira lista |
| Carregando | skeleton com a forma do conteúdo; spinner só para ações curtas |

---

## Acessibilidade (WCAG 2.2 AA) — checklist

- [ ] Contraste: texto 4.5:1; texto grande, ícones e bordas de controles 3:1
- [ ] Tudo funciona só com teclado, na ordem visual; foco sempre visível; Esc fecha camadas; sem armadilha de foco
- [ ] Elemento focado nunca fica escondido atrás de header fixo (`scroll-padding-top`)
- [ ] Alvos ≥ 24×24px (ideal 44)
- [ ] Imagens com `alt` descritivo; decorativas com `alt=""`; ícones decorativos com `aria-hidden="true"`
- [ ] Botão só com ícone tem `aria-label`
- [ ] Formulários: `label`, erro associado e anunciado (`aria-live`), foco no primeiro erro ao enviar
- [ ] Informação nunca só por cor (acrescente ícone ou texto)
- [ ] Zoom de 200% sem quebrar; **nunca** `user-scalable=no` ou `maximum-scale=1`
- [ ] ARIA só quando o HTML nativo não resolve

## Performance (Core Web Vitals: LCP ≤ 2.5s · INP ≤ 200ms · CLS ≤ 0.1)

- Imagens em AVIF/WebP com `width` e `height`; `loading="lazy"` abaixo da dobra; `fetchpriority="high"` na imagem principal; `srcset`/`sizes`.
- Fontes: no máximo 2 famílias, `preconnect`, `font-display: swap`, prefira fontes variáveis.
- Reserve espaço para mídia e embeds (`aspect-ratio`) para não haver deslocamento de layout.
- Carregue só o JS necessário; divida por rota; não use biblioteca para o que CSS faz.
- Listas longas: `content-visibility: auto` ou virtualização.
- Handlers rápidos: trabalho pesado fora do clique (debounce, `requestIdleCallback`, Web Worker).

## Responsividade

- Mobile-first: estilos base para 360px; aumente com `min-width`.
- Breakpoints pelo conteúdo (onde o layout quebra), não por aparelho. Referência: 40rem, 64rem, 80rem.
- Verifique em 360, 390, 768, 1024 e 1440px.
- Nunca rolagem horizontal na página; `min-width: 0` em filhos flex com texto; `overflow-wrap` em textos longos.
- Layout de borda a borda: `env(safe-area-inset-*)`.

---

## Fase 5 — Revisão (autocrítica obrigatória)

**Se você consegue tirar screenshots** (Playwright instalado):

```bash
npx playwright install chromium
npx playwright screenshot --viewport-size=390,844 http://localhost:5173 shot-mobile.png
npx playwright screenshot --viewport-size=1440,900 --full-page http://localhost:5173 shot-desktop.png
```

Analise as imagens. **Se não consegue ver imagens,** peça ao usuário um print e, enquanto isso, rode o checklist abaixo.

Procure valores soltos fora dos tokens:

```bash
grep -rnE "#[0-9a-fA-F]{3,8}\b|rgb\(|[0-9]+px" src --include=*.css | grep -v tokens.css
```

Checklist:
- [ ] **Teste do espelho:** remova um enfeite. Sobrou um único elemento memorável?
- [ ] **Teste do olho semicerrado:** a hierarquia continua clara (título → ação principal → resto)?
- [ ] Algum item da lista 2.3 (IA) ou 2.4 (antiquado) apareceu?
- [ ] Espaçamentos consistentes com a escala? Alinhamentos na mesma grade?
- [ ] Todos os estados existem (vazio, erro, carregando)?
- [ ] Tema escuro revisado (se houver)?
- [ ] Textos são reais, específicos e na voz da marca?

---

## Fase 6 — Testes

**O que testar:** cada estado do componente (carregando/vazio/erro/sucesso), validação e envio de formulários, navegação por teclado (Tab, Enter, Esc), comportamento crítico no mobile (menu), ausência de erros no console e de violações de acessibilidade.

**Regras:** consulte elementos como o usuário os percebe — por papel e rótulo (`getByRole`, `getByLabelText`), nunca por classe CSS. Teste comportamento, não implementação.

### Teste de componente (Vitest + Testing Library)

Pré-requisitos: `npm i -D vitest jsdom @testing-library/react @testing-library/user-event @testing-library/jest-dom @vitejs/plugin-react` e esta configuração (sem `globals: true` a tela de um teste vaza para o próximo e aparecem "múltiplos elementos"):

```ts
// vitest.config.ts
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  test: { environment: "jsdom", globals: true, setupFiles: ["./vitest.setup.ts"] },
});
```

```ts
// vitest.setup.ts
import "@testing-library/jest-dom/vitest";
```

```tsx
// src/components/SignupForm.test.tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { SignupForm } from "./SignupForm";

describe("SignupForm", () => {
  it("mostra erro quando o e-mail é inválido", async () => {
    const user = userEvent.setup();
    render(<SignupForm onSubmit={vi.fn()} />);

    await user.type(screen.getByLabelText(/e-mail/i), "abc");
    await user.click(screen.getByRole("button", { name: /criar conta/i }));

    expect(await screen.findByText(/informe um e-mail válido/i)).toBeInTheDocument();
  });

  it("envia os dados quando o formulário é válido", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn();
    render(<SignupForm onSubmit={onSubmit} />);

    await user.type(screen.getByLabelText(/e-mail/i), "ana@exemplo.com");
    await user.click(screen.getByRole("button", { name: /criar conta/i }));

    expect(onSubmit).toHaveBeenCalledWith({ email: "ana@exemplo.com" });
  });
});
```

### Teste ponta a ponta + acessibilidade (Playwright + axe)

Pré-requisitos: `npm i -D @playwright/test @axe-core/playwright` e `npx playwright install chromium`; `baseURL` configurada no `playwright.config.ts`.

```ts
// e2e/home.spec.ts
import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

test.describe("Página inicial", () => {
  test("carrega sem erros de console e sem violações de acessibilidade", async ({ page }) => {
    const errors: string[] = [];
    page.on("console", (msg) => {
      if (msg.type() === "error") errors.push(msg.text());
    });

    await page.goto("/");
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();

    const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag22aa"]).analyze();
    expect(results.violations).toEqual([]);
    expect(errors).toEqual([]);
  });

  test("menu mobile abre e fecha pelo teclado", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto("/");

    const toggle = page.getByRole("button", { name: /menu/i });
    await toggle.focus();
    await page.keyboard.press("Enter");
    await expect(toggle).toHaveAttribute("aria-expanded", "true");

    await page.keyboard.press("Escape");
    await expect(toggle).toHaveAttribute("aria-expanded", "false");
  });
});
```

Sem React (HTML/JS puro): teste funções puras com Vitest e a página com Playwright do mesmo jeito.

---

## Fase 7 — Verificação final e relatório

```bash
npm run build
npm test
npx playwright test
npx lighthouse http://localhost:4173 --only-categories=performance,accessibility --quiet --chrome-flags="--headless"
```

- [ ] Build sem erros nem avisos novos; testes verdes (saída colada)
- [ ] Revisado em 390px e 1440px; claro e escuro (se houver)
- [ ] Navegação completa só por teclado
- [ ] Sem valores fora dos tokens; sem `console.log` esquecido

```markdown
## Entregue
## Direção visual aplicada (1–2 frases)
## Evidência (saída dos comandos / screenshots)
## Como rodar
## Pendências
```

---

## Antipadrões — NUNCA faça

- Cor, tamanho ou espaçamento fora dos tokens
- `outline: none` sem substituto de foco visível
- `div`/`span` com clique no lugar de `button`/`a`
- Placeholder no lugar de rótulo
- Imagem sem `width`/`height` ou sem `alt`
- `transition: all`; animar `top/left/width/height`
- Mais de um botão primário competindo na mesma tela
- Bloquear zoom ou bloquear colar em campos
- Texto cinza claro sobre branco (contraste baixo)
- Modal para tudo; `alert()` nativo
- Ação destrutiva imediata, sem confirmação ou desfazer
- Datas/moedas formatadas à mão (use `Intl`)
- Copiar o visual padrão de uma biblioteca de componentes sem trocar tokens

---

*Baseado em: anthropics/skills (frontend-design), vercel-labs/web-interface-guidelines (web-design-guidelines), obra/superpowers (brainstorming, verification-before-completion), WCAG 2.2 e Core Web Vitals.*
