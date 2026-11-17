---
name: game-3d
description: Fluxo para criar jogos web (2D e 3D) e qualquer experiência 3D no navegador com Three.js — cenas, visualizadores de produto, hero 3D em site, modelagem procedural, personagens, cenários, câmera, animação, física, shaders, importação de modelos glTF/GLB do Blender e otimização. Cobre levantamento (mini-GDD), plano, arquitetura de jogo (loop de passo fixo, input por ações, estados), implementação, game feel, HUD, performance e testes. Use SEMPRE que a tarefa mencionar jogo, game, Three.js, WebGL, WebGPU, 3D, canvas, sprite, personagem, cena, modelo 3D, Blender, glTF/GLB, física ou React Three Fiber. Para menus, HUD e telas em HTML, combine com a skill frontend-ui.
---

# Game & 3D

Você atua como **desenvolvedor de jogos e engenheiro gráfico sênior**. Seu objetivo: algo **jogável e fluido primeiro**, bonito em seguida, sempre rodando a 60 FPS no aparelho alvo.

## 0. Regras de ouro

1. **Separe simulação de renderização.** A lógica (posições, regras, colisão, pontuação) é TS/JS puro em `sim/`, sem `three` e sem DOM — por isso é testável. O Three.js só **desenha** o estado.
2. **Jogável antes de bonito.** Cubos cinzas com o ciclo completo (jogar → ganhar/perder → recomeçar) antes de arte, efeitos e menus.
3. **Não invente API do Three.js.** Ela muda entre versões. Confira a versão (`npm ls three` ou o importmap) e, na dúvida, procure em `node_modules/three/src` ou na documentação. Nunca misture imports de `three` e `three/webgpu`.
4. **Ignore exemplos antigos da internet** que usem: `THREE.Geometry`, `examples/js/`, `renderer.outputEncoding`, `THREE.sRGBEncoding`, `physicallyCorrectLights`, `useLegacyLights`, `PCFSoftShadowMap` (removido), `RGBELoader` (obsoleto), `THREE.Clock` (obsoleto). Hoje: `BufferGeometry`, `three/addons/...`, `renderer.outputColorSpace`, `THREE.SRGBColorSpace`, luzes com intensidade física, sombra padrão (`PCFShadowMap`), `HDRLoader`, `THREE.Timer` ou o timestamp do `setAnimationLoop`.
5. **Use `dt` em todo movimento.** Velocidade nunca pode depender do FPS.
6. **Nada de alocação dentro do loop** (`new Vector3()` a cada frame). Reutilize objetos.
7. **Limpe o que criar:** `dispose()` em geometria, material e textura ao remover.
8. **Passos pequenos:** rode o jogo depois de cada passo. Evidência antes de "pronto".
9. **Pare nos portões 🛑.** Ao editar, escreva o bloco completo (nunca "... resto igual ...").

## Mapa do fluxo

```
Levantamento (mini-GDD) 🛑 → Plano + arquitetura 🛑 → Protótipo cinza jogável → Modelagem/arte → Game feel → HUD/menus → Performance → Testes → Relatório
```

**3D que não é jogo** (visualizador de produto, hero 3D em site): troque o mini-GDD por um brief curto (objetivo, interação, aparelho alvo, alternativa sem WebGL) e vá direto às Fases 4, 5 e 8.

---

## Fase 1 — Levantamento (mini-GDD) 🛑

Perguntas (até 3 por vez, cada uma com um padrão):
- Gênero e referência ("parecido com X, mas com Y")?
- 2D ou 3D? Câmera: primeira pessoa, terceira pessoa, isométrica, top-down, lateral?
- Plataforma e controles: desktop (teclado/mouse), mobile (toque), gamepad?
- Estilo visual: low-poly, toon, voxel, pixel art, realista (realista é caro — desaconselhe no MVP)?
- Tem modelos/sons prontos ou será procedural/gratuito?

Saída obrigatória:

```markdown
## Mini-GDD: <nome>
**Fantasia em 1 frase:** o que o jogador sente e faz
**Core loop:** ação → recompensa → progressão
**Controles:** ação | teclado | gamepad | toque
**Regras:** objetivo, como ganha, como perde
**Entidades:** jogador, inimigos, itens, cenário (1 linha de comportamento cada)
**Câmera:** tipo e comportamento
**Estilo visual e sonoro:** direção + 3 referências
**MVP (fatia vertical):** o mínimo jogável de ponta a ponta
**Depois do MVP:** lista priorizada
**Alvo de performance:** 60 FPS em <aparelho>
```

Termine com **"🛑 Aprova o mini-GDD?"**

---

## Fase 2 — Plano + arquitetura 🛑

### 2.1 Escolha da tecnologia

| Caso | Use |
|---|---|
| Jogo 2D simples (puzzle, arcade) | Canvas 2D puro |
| Jogo 2D completo (tilemaps, física, muitas cenas) | Phaser |
| 3D em site / visualizador | Three.js com `WebGLRenderer` |
| Jogo 3D | Vite + TypeScript + Three.js (+ Rapier se precisar de física real) |
| Projeto já em React | React Three Fiber + drei |
| Compute shaders, milhões de partículas | `WebGPURenderer` (`three/webgpu`) + TSL, testando o fallback |

**Padrão: `WebGLRenderer`** — máxima compatibilidade e mais exemplos. O `WebGPURenderer` cai para WebGL2 sozinho quando não há WebGPU, mas shaders GLSL próprios (`ShaderMaterial`) não rodam nele: precisam ser reescritos em TSL.

### 2.2 Estrutura de pastas

```
src/
  main.ts              # liga tudo: renderer, loop, input, estados
  core/
    loop.ts            # loop de passo fixo
    input.ts           # teclas/toque/gamepad → ações
    state-machine.ts   # boot, loading, menu, playing, paused, gameover
    rng.ts             # aleatório com seed
  sim/                 # LÓGICA PURA (sem three, sem DOM) — 100% testável
    world.ts
    collision.ts
  render/              # tudo que importa three
    renderer.ts
    camera.ts
    models/            # modelagem procedural
    dispose.ts
  assets/loader.ts
  audio/audio.ts
  ui/                  # HUD e menus em DOM (siga a skill frontend-ui)
public/models  public/textures  public/sounds
tests/
```

Criar projeto:

```bash
npm create vite@latest meu-jogo -- --template vanilla-ts
cd meu-jogo
npm i three
npm i -D @types/three vitest
```

### 2.3 Plano

Tarefas pequenas, cada uma com arquivos, interfaces e teste (o mesmo formato de plano da skill backend-dev). Ordem típica: loop + input + cubo se movendo → regras de ganhar/perder → câmera → estados e reinício → modelos → feel → HUD → som → performance.

Termine com **"🛑 Posso começar pelo protótipo cinza?"**

---

## Fase 3 — Arquitetura do jogo (código-base)

### 3.1 Loop de passo fixo

Física e regras rodam em passo fixo (determinístico); o desenho roda a cada frame e interpola.

```ts
// src/core/loop.ts
export type LoopCallbacks = {
  update: (dt: number) => void; // lógica, sempre com o mesmo dt
  render: (alpha: number) => void; // desenho; alpha 0..1 para interpolar
};

export function createFixedLoop(cb: LoopCallbacks, stepHz = 60) {
  const step = 1 / stepHz;
  const maxFrame = 0.25; // evita "espiral da morte" ao voltar de outra aba
  let acc = 0;
  let last: number | null = null;

  return {
    /** Chame a cada frame com o timestamp em ms (renderer.setAnimationLoop ou requestAnimationFrame). */
    tick(nowMs: number) {
      const now = nowMs / 1000;
      const frameTime = last === null ? 0 : Math.min(now - last, maxFrame);
      last = now;
      acc += frameTime;
      while (acc >= step) {
        cb.update(step);
        acc -= step;
      }
      cb.render(acc / step);
    },
    /** Chame ao pausar/retomar para não "pular" o tempo parado. */
    reset() {
      acc = 0;
      last = null;
    },
  };
}
```

### 3.2 Input por ações (nunca teste teclas direto na lógica)

```ts
// src/core/input.ts
import type { Intent } from "../sim/world";

export type Action = "left" | "right" | "up" | "down" | "jump" | "pause";

const KEYMAP: Record<string, Action> = {
  ArrowLeft: "left", KeyA: "left",
  ArrowRight: "right", KeyD: "right",
  ArrowUp: "up", KeyW: "up",
  ArrowDown: "down", KeyS: "down",
  Space: "jump",
  Escape: "pause", KeyP: "pause",
};

export class Input {
  private down = new Set<Action>();
  private pressed = new Set<Action>(); // só no frame em que apertou

  constructor(target: Window = window) {
    target.addEventListener("keydown", (e) => {
      const action = KEYMAP[e.code]; // e.code = tecla física: WASD funciona em qualquer layout
      if (!action) return;
      e.preventDefault();
      if (!this.down.has(action)) this.pressed.add(action);
      this.down.add(action);
    });
    target.addEventListener("keyup", (e) => {
      const action = KEYMAP[e.code];
      if (action) this.down.delete(action);
    });
    target.addEventListener("blur", () => this.down.clear());
  }

  isDown(a: Action) { return this.down.has(a); }
  wasPressed(a: Action) { return this.pressed.has(a); }
  /** Chame no fim de cada update. */
  endFrame() { this.pressed.clear(); }
}

export function readIntent(input: Input): Intent {
  return {
    moveX: (input.isDown("right") ? 1 : 0) - (input.isDown("left") ? 1 : 0),
    moveZ: (input.isDown("down") ? 1 : 0) - (input.isDown("up") ? 1 : 0),
    jump: input.wasPressed("jump"),
  };
}
```

- **Gamepad:** leia `navigator.getGamepads()` a cada update; zona morta de 0.15 nos analógicos.
- **Toque:** use Pointer Events (unificam mouse e toque); joystick virtual ou zonas de toque; `touch-action: none` no canvas.
- Mostre os controles na tela e permita remapear quando possível.

### 3.3 Simulação pura

```ts
// src/sim/world.ts  — sem three, sem DOM
export type Intent = { moveX: number; moveZ: number; jump: boolean };
export type Player = { x: number; y: number; z: number; vy: number; onGround: boolean };
export type World = { player: Player; score: number; time: number };

const SPEED = 6; // m/s
const GRAVITY = -25; // m/s²
const JUMP_VELOCITY = 9; // m/s

export function createWorld(): World {
  return { player: { x: 0, y: 0, z: 0, vy: 0, onGround: true }, score: 0, time: 0 };
}

export function stepWorld(w: World, intent: Intent, dt: number): void {
  const p = w.player;
  const len = Math.max(1, Math.hypot(intent.moveX, intent.moveZ)); // diagonal não fica mais rápida
  p.x += (intent.moveX / len) * SPEED * dt;
  p.z += (intent.moveZ / len) * SPEED * dt;

  if (intent.jump && p.onGround) {
    p.vy = JUMP_VELOCITY;
    p.onGround = false;
  }
  p.vy += GRAVITY * dt;
  p.y += p.vy * dt;
  if (p.y <= 0) {
    p.y = 0;
    p.vy = 0;
    p.onGround = true;
  }
  w.time += dt;
}
```

```ts
// src/sim/collision.ts
export type AABB = { minX: number; minY: number; minZ: number; maxX: number; maxY: number; maxZ: number };

export function aabbOverlap(a: AABB, b: AABB): boolean {
  return a.minX < b.maxX && a.maxX > b.minX &&
         a.minY < b.maxY && a.maxY > b.minY &&
         a.minZ < b.maxZ && a.maxZ > b.minZ;
}
```

### 3.4 Estados do jogo

```ts
// src/core/state-machine.ts
export type GameState = "boot" | "loading" | "menu" | "playing" | "paused" | "gameover";

const ALLOWED: Record<GameState, GameState[]> = {
  boot: ["loading"],
  loading: ["menu"],
  menu: ["playing"],
  playing: ["paused", "gameover"],
  paused: ["playing", "menu"],
  gameover: ["playing", "menu"],
};

type Hooks = Partial<Record<GameState, { enter?: () => void; exit?: () => void }>>;

export class StateMachine {
  private current: GameState;
  private hooks: Hooks;

  constructor(hooks: Hooks = {}, initial: GameState = "boot") {
    this.hooks = hooks;
    this.current = initial;
  }

  get state(): GameState {
    return this.current;
  }

  go(next: GameState): void {
    if (!ALLOWED[this.current].includes(next)) {
      throw new Error(`Transição inválida: ${this.current} → ${next}`);
    }
    this.hooks[this.current]?.exit?.();
    this.current = next;
    this.hooks[next]?.enter?.();
  }
}
```

### 3.5 Aleatório com seed (fases reproduzíveis e testáveis)

```ts
// src/core/rng.ts — mulberry32
export function createRng(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
```

### 3.6 Ligando tudo

```ts
// src/main.ts
import * as THREE from "three";
import { Input, readIntent } from "./core/input";
import { createFixedLoop } from "./core/loop";
import { createRenderer } from "./render/renderer";
import { createWorld, stepWorld } from "./sim/world";

const container = document.getElementById("game") as HTMLElement;
const { renderer, scene, camera } = createRenderer(container);
const input = new Input();
const world = createWorld();

const player = new THREE.Mesh(new THREE.BoxGeometry(1, 1, 1), new THREE.MeshStandardMaterial({ color: 0x8899aa }));
player.geometry.translate(0, 0.5, 0); // pivô nos pés
scene.add(player);
camera.position.set(0, 6, 10);
camera.lookAt(0, 0, 0);

const prev = new THREE.Vector3();
const curr = new THREE.Vector3();

const loop = createFixedLoop({
  update(dt) {
    prev.set(world.player.x, world.player.y, world.player.z);
    stepWorld(world, readIntent(input), dt);
    input.endFrame();
  },
  render(alpha) {
    curr.set(world.player.x, world.player.y, world.player.z);
    player.position.lerpVectors(prev, curr, alpha); // movimento suave em qualquer taxa de atualização
    renderer.render(scene, camera);
  },
});

renderer.setAnimationLoop((t) => loop.tick(t));

document.addEventListener("visibilitychange", () => {
  if (document.hidden) renderer.setAnimationLoop(null);
  else {
    loop.reset();
    renderer.setAnimationLoop((t) => loop.tick(t));
  }
});
```

Também: **pool de objetos** para tiros/inimigos/partículas (reaproveite com `visible = false`); **save** em `localStorage` com chave versionada (`meujogo:save:v1`) dentro de `try/catch`; em dev, exponha `window.__game = { state, fps }` para testes.

---

## Fase 4 — Three.js essencial

### 4.1 Renderer, cena e câmera

```ts
// src/render/renderer.ts
import * as THREE from "three";

export function createRenderer(container: HTMLElement) {
  const renderer = new THREE.WebGLRenderer({ antialias: true, powerPreference: "high-performance" });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2)); // nunca sem limite
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.shadowMap.enabled = true;
  container.appendChild(renderer.domElement);

  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(55, 1, 0.1, 500);

  const resize = () => {
    const w = container.clientWidth;
    const h = container.clientHeight;
    if (w === 0 || h === 0) return;
    renderer.setSize(w, h, false);
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
  };
  const observer = new ResizeObserver(resize);
  observer.observe(container);
  resize();

  return {
    renderer,
    scene,
    camera,
    dispose() {
      observer.disconnect();
      renderer.setAnimationLoop(null);
      renderer.dispose();
      renderer.domElement.remove();
    },
  };
}
```

CSS do canvas: `#game { position: fixed; inset: 0; } #game canvas { display: block; width: 100%; height: 100%; touch-action: none; }`

Sem bundler (importmap) — descubra a versão atual com `npm view three version` e fixe-a:

```html
<script type="importmap">
  { "imports": {
      "three": "https://cdn.jsdelivr.net/npm/three@0.186.1/build/three.module.js",
      "three/addons/": "https://cdn.jsdelivr.net/npm/three@0.186.1/examples/jsm/"
  } }
</script>
<script type="module" src="./main.js"></script>
```

### 4.2 Luz e ambiente

Intensidades são físicas: `DirectionalLight` ~1–3; `HemisphereLight` ~0.5–1.5; `PointLight`/`SpotLight` precisam de valores bem maiores (dezenas a centenas) com `decay = 2`.

```ts
const sun = new THREE.DirectionalLight(0xffffff, 2.5);
sun.position.set(10, 20, 10);
sun.castShadow = true;
sun.shadow.mapSize.set(2048, 2048); // 1024 no mobile
const sc = sun.shadow.camera; // cubra SÓ a área de jogo
sc.left = -20; sc.right = 20; sc.top = 20; sc.bottom = -20; sc.near = 1; sc.far = 60;
sun.shadow.bias = -0.0005;
sun.shadow.normalBias = 0.02;
scene.add(new THREE.HemisphereLight(0xdfe8ff, 0x3a3128, 1.0), sun);
scene.fog = new THREE.Fog(0xbfd4e6, 30, 120); // dá profundidade; use a mesma cor no fundo
scene.background = new THREE.Color(0xbfd4e6);
```

Para materiais PBR, dê um ambiente de reflexo:

```ts
import { RoomEnvironment } from "three/addons/environments/RoomEnvironment.js";

const pmrem = new THREE.PMREMGenerator(renderer);
scene.environment = pmrem.fromScene(new RoomEnvironment(), 0.04).texture;
```

Para céu/iluminação realista, use um HDRI (Poly Haven) com `HDRLoader` de `three/addons/loaders/HDRLoader.js` (em versões anteriores à r180 o nome era `RGBELoader` — confira em `node_modules/three/examples/jsm/loaders/`).

### 4.3 Materiais por estilo

| Estilo | Material | Dicas |
|---|---|---|
| Low-poly | `MeshStandardMaterial({ flatShading: true })` | cores sólidas ou vertex colors, sem textura |
| Toon | `MeshToonMaterial` + `gradientMap` de 3–4 tons (`NearestFilter`) | contorno: cópia da malha em `BackSide`, levemente maior, preta |
| PBR/realista | `MeshStandardMaterial` / `MeshPhysicalMaterial` | mapas ORM; `scene.environment` obrigatório |
| Sem luz (efeitos, UI 3D) | `MeshBasicMaterial` | o mais barato |

Compartilhe a mesma instância de material entre malhas iguais.

### 4.4 Câmera

```ts
// src/render/camera.ts — câmera de terceira pessoa com suavização independente do FPS
import * as THREE from "three";

const _desired = new THREE.Vector3();
const _offset = new THREE.Vector3(0, 4, 8);

export function followCamera(camera: THREE.Camera, target: THREE.Object3D, dt: number, sharpness = 6) {
  _desired.copy(_offset).applyQuaternion(target.quaternion).add(target.position);
  const t = 1 - Math.exp(-sharpness * dt); // nunca use lerp com fator fixo
  camera.position.lerp(_desired, t);
  camera.lookAt(target.position);
}
```

- Visualizador: `OrbitControls` com `enableDamping = true` e `controls.update()` a cada frame.
- FPS: `PointerLockControls`. Campo de visão: 50–60 (terceira pessoa), 70–90 (primeira pessoa, ajustável).

### 4.5 Interação, animação, física

- **Clique/hover em 3D:** `Raycaster` com coordenadas normalizadas pelo `getBoundingClientRect()` do canvas; teste só contra a lista de objetos interativos, nunca a cena inteira.
- **Animações de modelos:**

```ts
export function createAnimator(model: THREE.Object3D, clips: THREE.AnimationClip[]) {
  const mixer = new THREE.AnimationMixer(model);
  const actions = new Map(clips.map((clip) => [clip.name, mixer.clipAction(clip)]));
  let current: THREE.AnimationAction | undefined;

  return {
    play(name: string, fade = 0.2) {
      const next = actions.get(name);
      if (!next || next === current) return;
      next.reset().play();
      if (current) current.crossFadeTo(next, fade, false);
      current = next;
    },
    update(dt: number) {
      mixer.update(dt);
    },
  };
}
```

- **Física:** arcade simples → colisão própria em `sim/` (AABB/esferas, testável). Física real → Rapier (`@dimforge/rapier3d-compat`): avance o mundo físico no `update` com o dt fixo e copie posições para as malhas no `render`. Use colisores primitivos (caixa, esfera, cápsula); nunca malha detalhada em corpo dinâmico.
- **Pós-processamento** (bloom etc.): `EffectComposer` + `RenderPass` + efeito + `OutputPass`. Custa caro — use pouco e desligue no mobile.

### 4.6 React Three Fiber (se o projeto for React)

- `<Canvas dpr={[1, 2]} shadows>`; câmera e luzes como componentes.
- `useFrame((state, delta) => { ref.current.rotation.y += delta; })` — altere refs; **nunca `setState` a cada frame**.
- drei: `useGLTF` (+ `useGLTF.preload`), `Environment`, `OrbitControls`, `Html`.
- Visualizador estático: `frameloop="demand"`.

### 4.7 WebGPURenderer (opcional)

```ts
import * as THREE from "three/webgpu"; // TODOS os imports de three vêm daqui (e de "three/tsl")

const renderer = new THREE.WebGPURenderer({ antialias: true });
await renderer.init(); // ou use setAnimationLoop, que inicializa sozinho
```

Misturar `three` com `three/webgpu` cria classes diferentes que não se reconhecem (ex.: luzes que silenciosamente não iluminam). Teste o fallback com `new THREE.WebGPURenderer({ forceWebGL: true })`.

### 4.8 Limpeza e robustez

```ts
// src/render/dispose.ts — só para objetos cujos materiais/geometrias NÃO são compartilhados
import * as THREE from "three";

export function disposeObject(root: THREE.Object3D): void {
  root.traverse((obj) => {
    if (!(obj instanceof THREE.Mesh)) return;
    obj.geometry.dispose();
    const materials = Array.isArray(obj.material) ? obj.material : [obj.material];
    for (const material of materials) {
      for (const value of Object.values(material)) {
        if (value instanceof THREE.Texture) value.dispose();
      }
      material.dispose();
    }
  });
  root.removeFromParent();
}
```

- Sem WebGL: envolva a criação do renderer em `try/catch` e mostre mensagem ou imagem estática.
- Trate `webglcontextlost` no canvas (pause e avise).
- 3D dentro de site: pause quando o canvas sai da tela (`IntersectionObserver`) e quando a aba fica oculta.
- `prefers-reduced-motion`: desligue rotação automática, tremor de câmera e parallax.
- 3D decorativo em site precisa de alternativa textual (`aria-label` ou texto ao lado).

---

## Fase 5 — Modelagem 3D

### 5.1 Procedural (no código) — ideal para protótipo e estilo low-poly

- **Composição:** um `Group` é o objeto; filhos são as partes (primitivas).
- **Pivô no lugar certo:** pés (personagem), base (prop), dobradiça (porta), ombro (braço). Posicione as partes *em relação ao pivô*.
- **Escala real:** 1 unidade = 1 metro. Personagem ~1.8; porta 2.1; degrau 0.18.
- **Silhueta primeiro:** proporções legíveis de longe; detalhe depois.
- **Paleta limitada** (4–6 cores) num objeto `PALETTE`; materiais compartilhados.
- **Primitivas úteis:** `BoxGeometry`, `CapsuleGeometry`, `CylinderGeometry` (poucos segmentos = low-poly), `ConeGeometry`, `IcosahedronGeometry` (pedras, detail 0–1), `LatheGeometry` (vasos, garrafas, troncos), `ExtrudeGeometry` (forma 2D → 3D), `TubeGeometry` (canos, trilhos ao longo de uma curva).
- **Muitas cópias iguais** (pedras, árvores, grama): `InstancedMesh`. Muitas peças estáticas diferentes: `mergeGeometries` de `three/addons/utils/BufferGeometryUtils.js` → 1 chamada de desenho.

Personagem articulado (o `Group` é a articulação; a malha fica pendurada nele):

```ts
// src/render/models/character.ts
import * as THREE from "three";

export type CharacterRig = {
  root: THREE.Group;
  leftLeg: THREE.Group; rightLeg: THREE.Group;
  leftArm: THREE.Group; rightArm: THREE.Group;
};

export function createCharacter(color = 0x3b6fd8): CharacterRig {
  const cloth = new THREE.MeshStandardMaterial({ color, flatShading: true });
  const skin = new THREE.MeshStandardMaterial({ color: 0xf2c6a0, flatShading: true });
  const root = new THREE.Group(); // pivô nos pés (y = 0)

  const torso = new THREE.Mesh(new THREE.BoxGeometry(0.6, 0.7, 0.35), cloth);
  torso.position.y = 1.05;
  const head = new THREE.Mesh(new THREE.BoxGeometry(0.4, 0.4, 0.4), skin);
  head.position.y = 1.65;
  root.add(torso, head);

  const limb = (w: number, h: number, mat: THREE.Material, x: number, y: number) => {
    const joint = new THREE.Group();
    joint.position.set(x, y, 0);
    const mesh = new THREE.Mesh(new THREE.BoxGeometry(w, h, w), mat);
    mesh.position.y = -h / 2;
    joint.add(mesh);
    root.add(joint);
    return joint;
  };

  const rig: CharacterRig = {
    root,
    leftLeg: limb(0.22, 0.7, cloth, -0.15, 0.7),
    rightLeg: limb(0.22, 0.7, cloth, 0.15, 0.7),
    leftArm: limb(0.18, 0.65, skin, -0.42, 1.38),
    rightArm: limb(0.18, 0.65, skin, 0.42, 1.38),
  };
  root.traverse((o) => {
    if (o instanceof THREE.Mesh) o.castShadow = true;
  });
  return rig;
}

/** Caminhada procedural: chame no render. speed de 0 (parado) a 1 (correndo). */
export function animateWalk(rig: CharacterRig, time: number, speed: number) {
  const swing = Math.sin(time * 9) * 0.7 * speed;
  rig.leftLeg.rotation.x = swing;
  rig.rightLeg.rotation.x = -swing;
  rig.leftArm.rotation.x = -swing * 0.8;
  rig.rightArm.rotation.x = swing * 0.8;
}
```

Cenário com instâncias e terreno com ruído:

```ts
// src/render/models/environment.ts
import * as THREE from "three";
import { createNoise2D } from "simplex-noise";

export function scatterRocks(count: number, area: number, rng: () => number): THREE.InstancedMesh {
  const rocks = new THREE.InstancedMesh(
    new THREE.IcosahedronGeometry(0.4, 0),
    new THREE.MeshStandardMaterial({ color: 0x8a8f98, flatShading: true }),
    count,
  );
  const m = new THREE.Matrix4();
  const p = new THREE.Vector3();
  const q = new THREE.Quaternion();
  const s = new THREE.Vector3();
  const e = new THREE.Euler();
  for (let i = 0; i < count; i++) {
    p.set((rng() - 0.5) * area, 0.1, (rng() - 0.5) * area);
    q.setFromEuler(e.set(rng() * Math.PI, rng() * Math.PI, 0));
    const k = 0.5 + rng() * 1.2;
    s.set(k, k * (0.6 + rng() * 0.4), k);
    rocks.setMatrixAt(i, m.compose(p, q, s));
  }
  rocks.instanceMatrix.needsUpdate = true;
  rocks.castShadow = true;
  rocks.receiveShadow = true;
  return rocks;
}

export function createTerrain(size: number, segments: number, rng: () => number): THREE.Mesh {
  const noise2D = createNoise2D(rng); // npm i simplex-noise
  const geometry = new THREE.PlaneGeometry(size, size, segments, segments);
  geometry.rotateX(-Math.PI / 2);
  const pos = geometry.attributes.position;
  for (let i = 0; i < pos.count; i++) {
    const x = pos.getX(i);
    const z = pos.getZ(i);
    pos.setY(i, noise2D(x * 0.02, z * 0.02) * 4 + noise2D(x * 0.08, z * 0.08) * 0.8);
  }
  geometry.computeVertexNormals();
  const terrain = new THREE.Mesh(geometry, new THREE.MeshStandardMaterial({ color: 0x6a8f4e, flatShading: true }));
  terrain.receiveShadow = true;
  return terrain;
}
```

Se a jogabilidade depende da altura do terreno, a função de altura mora em `sim/` e é usada **tanto** pelo render quanto pela lógica.

### 5.2 Modelos externos (Blender → glTF)

Checklist de exportação no Blender:
- [ ] Formato **glTF 2.0 binário (.glb)**, opção "+Y Up" ligada (padrão)
- [ ] 1 unidade = 1 metro; **aplique as transformações** (Ctrl+A → All Transforms)
- [ ] Origem nos pés/base; modelo de frente para a vista *Front* (numpad 1) — vira +Z no glTF
- [ ] Modificadores aplicados; normais para fora; faces escondidas removidas
- [ ] Nomes claros em objetos e animações (`Idle`, `Walk`, `Run`, `Jump`, `Attack`) — o código busca por nome
- [ ] Texturas em potência de 2 (512/1024/2048); cor em sRGB; normal/rugosidade/metal lineares; pacote ORM (R=oclusão, G=rugosidade, B=metal)
- [ ] Animações exportadas (todas as actions); no máximo 4 influências de osso por vértice

Otimize antes de usar:

```bash
npx @gltf-transform/cli inspect modelo.glb
npx @gltf-transform/cli optimize modelo.glb modelo.opt.glb --compress meshopt --texture-compress webp --texture-size 1024
```

Carregue:

```ts
// src/assets/loader.ts
import * as THREE from "three";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import { MeshoptDecoder } from "three/addons/libs/meshopt_decoder.module.js";

export function createLoader(onProgress: (ratio: number) => void) {
  const manager = new THREE.LoadingManager();
  manager.onProgress = (_url, loaded, total) => onProgress(loaded / total);
  const gltfLoader = new GLTFLoader(manager);
  gltfLoader.setMeshoptDecoder(MeshoptDecoder);

  return {
    async model(url: string) {
      const gltf = await gltfLoader.loadAsync(url);
      gltf.scene.traverse((o) => {
        if (o instanceof THREE.Mesh) {
          o.castShadow = true;
          o.receiveShadow = true;
        }
      });
      return gltf; // gltf.scene (objeto) e gltf.animations (clipes)
    },
  };
}
```

- Draco: `DRACOLoader` + `setDecoderPath(...)`; texturas KTX2: `KTX2Loader` + `setTranscoderPath(...)` + `detectSupport(renderer)`.
- Vários personagens do mesmo modelo com esqueleto: `import * as SkeletonUtils from "three/addons/utils/SkeletonUtils.js"` e `SkeletonUtils.clone(gltf.scene)` (o `.clone()` comum quebra o esqueleto).

**Assets gratuitos CC0:** Kenney, Quaternius (modelos e animações low-poly), Poly Haven (HDRIs, texturas, modelos), ambientCG (texturas PBR). Registre fonte e licença em `CREDITS.md`.

### 5.3 Orçamento (referência — meça no aparelho alvo)

| Item | Mobile | Desktop |
|---|---|---|
| Personagem principal | 3–8 mil triângulos | 10–30 mil |
| Inimigo comum | 1–3 mil | 5–10 mil |
| Objeto de cenário | 50–1 mil | até 5 mil |
| Cena visível inteira | ≤ 300 mil | ≤ 1–2 milhões |
| Texturas | ≤ 1024px | ≤ 2048px |
| Chamadas de desenho | ≤ 100 | ≤ 300 |

---

## Fase 6 — Game feel ("juice")

- **Controle responsivo:** o input reage no mesmo frame; aceleração e frenagem curtas (nem instantâneo, nem "sabão").
- **Plataforma:** *coyote time* (~0.1s após sair da borda ainda pode pular) e *buffer* de pulo (~0.1s antes de tocar o chão).
- **Feedback em camadas** para todo evento importante: visual (flash, partícula) + som + corpo (squash & stretch, recuo) + câmera (tremor curto, opcional).
- **Hit-stop:** congele 50–100ms em impactos fortes.
- **Tremor de câmera:** pequeno, decai rápido, desligável nas configurações.
- **Easing** em tudo que se move por script; nunca linear em efeitos.
- **Som:** efeitos curtos com variação de pitch ±5–10% para não cansar. Web Audio só destrava após o primeiro gesto do usuário; em 3D use `AudioListener` + `PositionalAudio`.
- **Clareza:** o jogador sempre sabe o que o atingiu, quanto de vida tem e o que fazer em seguida.

## Fase 7 — HUD e menus

- HUD em **DOM sobre o canvas** (texto nítido, acessível, fácil de estilizar) — siga a skill frontend-ui (tokens, contraste, foco).
- Contêiner do HUD com `pointer-events: none`; ative só nos botões.
- Atualize o DOM **só quando o valor muda**, nunca a cada frame.
- Menus navegáveis por teclado **e** gamepad, com foco visível.
- Pausa obrigatória (Esc/P/Start) e pausa automática ao trocar de aba.
- Configurações mínimas: volume (música/efeitos), sensibilidade, inverter Y, reduzir tremor/movimento, ver controles.
- Tela de carregamento com progresso real (`LoadingManager`).
- Mobile: botões de toque ≥ 48px, longe das bordas de gesto do sistema, respeitando `env(safe-area-inset-*)`.

### Jogos 2D

O mesmo loop, input, estados e testes valem. Canvas 2D: escale o canvas por `devicePixelRatio`; pixel art com `ctx.imageSmoothingEnabled = false` e escala inteira; sprites em atlas (uma imagem, vários quadros). Projetos 2D maiores: Phaser.

---

## Fase 8 — Performance

Meça: `renderer.info.render.calls`, `renderer.info.render.triangles`, `renderer.info.memory`; contador de FPS (stats.js) em dev; aba Performance do DevTools.

- [ ] `pixelRatio` ≤ 2 (mobile: 1.5 ou dinâmico se o FPS cair)
- [ ] Repetidos em `InstancedMesh`; estáticos fundidos com `mergeGeometries`
- [ ] Materiais e geometrias compartilhados
- [ ] Texturas pequenas e comprimidas (KTX2/WebP)
- [ ] Sombras: uma luz com sombra, câmera de sombra justa, `castShadow` só no que importa; cena estática → `sun.shadow.autoUpdate = false` e `sun.shadow.needsUpdate = true` quando mudar
- [ ] Zero alocação no loop (vetores temporários no módulo: `const _tmp = new THREE.Vector3()`)
- [ ] Nada de criar/remover objetos da cena a cada frame — use pool + `visible`
- [ ] `THREE.LOD` para objetos distantes
- [ ] Física com colisores primitivos e corpos "dormindo"
- [ ] Visualizador estático: renderize só quando algo muda

---

## Fase 9 — Testes

**Estratégia:**
- **Unitários (Vitest)** para tudo em `sim/` e `core/`: loop, estados, colisão, pontuação, geração com seed. Mesma seed + mesmos inputs = mesmo resultado.
- **Smoke de render (Playwright):** a página carrega, o canvas aparece, o jogo inicia, nada de erro no console.
- **Manual guiado:** começar → jogar → perder → recomeçar; pausar; redimensionar a janela; testar no celular.

### Classe de teste (Vitest)

```ts
// tests/core/loop.test.ts
import { describe, expect, it, vi } from "vitest";
import { createFixedLoop } from "../../src/core/loop";

describe("createFixedLoop", () => {
  it("executa 2 updates de passo fixo quando passam 40ms a 60Hz", () => {
    const update = vi.fn();
    const loop = createFixedLoop({ update, render: vi.fn() }, 60);

    loop.tick(0);
    loop.tick(40);

    expect(update).toHaveBeenCalledTimes(2);
    expect(update).toHaveBeenCalledWith(1 / 60);
  });

  it("limita frames longos para não travar ao voltar de outra aba", () => {
    const update = vi.fn();
    const render = vi.fn();
    const loop = createFixedLoop({ update, render }, 50);

    loop.tick(0);
    loop.tick(10_000);

    expect(update).toHaveBeenCalledTimes(12); // 0.25s / 0.02s
    expect(render.mock.calls.at(-1)?.[0]).toBeCloseTo(0.5);
  });
});
```

```ts
// tests/sim/world.test.ts
import { describe, expect, it } from "vitest";
import { createWorld, stepWorld } from "../../src/sim/world";

const DT = 1 / 60;
const run = (seconds: number, fn: () => void) => {
  for (let i = 0; i < Math.round(seconds / DT); i++) fn();
};

describe("stepWorld", () => {
  it("move o jogador 6 metros em 1 segundo", () => {
    const w = createWorld();

    run(1, () => stepWorld(w, { moveX: 1, moveZ: 0, jump: false }, DT));

    expect(w.player.x).toBeCloseTo(6, 5);
  });

  it("não fica mais rápido na diagonal", () => {
    const w = createWorld();

    run(1, () => stepWorld(w, { moveX: 1, moveZ: 1, jump: false }, DT));

    expect(Math.hypot(w.player.x, w.player.z)).toBeCloseTo(6, 5);
  });

  it("só pula quando está no chão", () => {
    const w = createWorld();
    stepWorld(w, { moveX: 0, moveZ: 0, jump: true }, DT);
    const vyAfterFirstJump = w.player.vy;

    stepWorld(w, { moveX: 0, moveZ: 0, jump: true }, DT);

    expect(vyAfterFirstJump).toBeGreaterThan(0);
    expect(w.player.vy).toBeLessThan(vyAfterFirstJump);
  });

  it("nunca atravessa o chão", () => {
    const w = createWorld();
    w.player.y = 5;

    run(3, () => stepWorld(w, { moveX: 0, moveZ: 0, jump: false }, DT));

    expect(w.player.y).toBe(0);
    expect(w.player.onGround).toBe(true);
  });
});
```

```ts
// tests/core/state-machine.test.ts
import { describe, expect, it, vi } from "vitest";
import { StateMachine } from "../../src/core/state-machine";

describe("StateMachine", () => {
  it("chama exit do estado atual e enter do próximo", () => {
    const exit = vi.fn();
    const enter = vi.fn();
    const sm = new StateMachine({ menu: { exit }, playing: { enter } }, "menu");

    sm.go("playing");

    expect(exit).toHaveBeenCalledOnce();
    expect(enter).toHaveBeenCalledOnce();
    expect(sm.state).toBe("playing");
  });

  it("recusa transição inválida", () => {
    const sm = new StateMachine({}, "menu");

    expect(() => sm.go("gameover")).toThrow(/inválida/);
  });
});
```

### Smoke de render (Playwright)

```ts
// e2e/game.spec.ts
import { expect, test } from "@playwright/test";

test("o jogo carrega e entra na partida sem erros", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  page.on("console", (m) => {
    if (m.type() === "error") errors.push(m.text());
  });

  await page.goto("/");
  await expect(page.locator("canvas")).toBeVisible();
  await page.keyboard.press("Enter"); // sai do menu
  await page.waitForFunction(() => (window as any).__game?.state === "playing");

  expect(errors).toEqual([]);
});
```

---

## Fase 10 — Verificação final e relatório

```bash
npm test
npx tsc --noEmit
npm run build
npx playwright test
```

- [ ] Testes verdes, tipos e build sem erro (saída colada)
- [ ] Ciclo completo jogado: começar → jogar → perder/ganhar → recomeçar
- [ ] Pausa (tecla e troca de aba) funciona
- [ ] Redimensionar a janela não distorce a imagem
- [ ] FPS e chamadas de desenho dentro do orçamento (números colados)
- [ ] Sem erros/avisos no console

```markdown
## Entregue
## Como jogar (controles)
## Evidência (testes, FPS, draw calls, screenshot)
## Como rodar
## Pendências / próximos passos do GDD
```

---

## Antipadrões — NUNCA faça

- Lógica de jogo dentro do render ou em `mesh.userData`
- Ignorar `dt` (jogo mais rápido em monitor de 144Hz)
- `new Vector3()` / `new Material()` dentro do loop
- Adicionar e remover objetos da cena o tempo todo sem pool
- Sombra em todas as luzes; `shadow.mapSize` 4096 no mobile
- `setPixelRatio(window.devicePixelRatio)` sem limite
- Misturar `three` com `three/webgpu`
- Copiar exemplo antigo (`THREE.Geometry`, `outputEncoding`, `examples/js`)
- Modelo de 20 MB sem compressão
- HUD de texto desenhado dentro do WebGL quando o DOM resolve
- Corpo físico dinâmico com malha detalhada
- Sem pausa ao trocar de aba
- Começar pela arte antes do loop jogável

---

*Baseado em: majidmanzarpour/threejs-game-skills, OpenAEC-Foundation/Three.js-Claude-Skill-Package, manual oficial do three.js (WebGPURenderer), documentação do glTF Transform e obra/superpowers (TDD e verificação).*
