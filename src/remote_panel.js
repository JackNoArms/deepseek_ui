// Painel remoto — SPA em JavaScript puro, sem dependências.
// Toda comunicação é com /api/*; o token está no cookie HttpOnly que / gravou.

'use strict';

const $ = (id) => document.getElementById(id);

function esc(t) {
  return String(t == null ? '' : t)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

function md(t) {
  let out = esc(t || '');
  out = out.replace(/```([^\n`]*)\n([\s\S]*?)```/g, (_, lang, code) =>
    `<pre data-lang="${esc(lang.trim())}"><code>${code}</code></pre>`);
  out = out.replace(/`([^`\n]+)`/g, '<code>$1</code>');
  out = out.replace(/\*\*([^*]+)\*\*/g, '<b>$1</b>');
  out = out.replace(/^(#{1,3})\s+(.*)$/gm, (_, h, txt) =>
    `<h${h.length}>${txt}</h${h.length}>`);
  return out;
}

let toastTimer = null;
function toast(msg, erro = false) {
  const el = $('toast');
  el.textContent = msg;
  el.classList.toggle('erro', !!erro);
  el.classList.add('show');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.remove('show'), 2600);
}

function toastErro(e, prefixo) {
  if (e && e.message === 'app_ocupado') {
    toast('App ocupado no PC — ' +
          (e.dica || 'tente de novo em alguns segundos.'), true);
    return;
  }
  const base = (e && e.message) || 'erro';
  toast((prefixo ? prefixo + base : 'Falha: ' + base), true);
}

async function get(rota) {
  const r = await fetch(rota, { credentials: 'same-origin' });
  if (r.status === 401) throw new Error('token inválido');
  return r.json();
}

async function post(rota, corpo) {
  const r = await fetch(rota, {
    method: 'POST', credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(corpo || {}),
  });
  const dados = await r.json().catch(() => ({}));
  if (dados && dados.erro) {
    const erro = new Error(dados.erro);
    if (dados.dica) erro.dica = dados.dica;
    throw erro;
  }
  if (!r.ok) throw new Error('HTTP ' + r.status);
  return dados;
}

// ---------- tema ----------
// Segue o tema do PC (`theme` no /api/state), a menos que este aparelho
// tenha escolhido outro na aba Mais (guardado só neste navegador).
let temaPC = '';
function temaLocal() {
  try { return localStorage.getItem('tema-local') || ''; } catch (e) { return ''; }
}
function aplicarTema() {
  const tema = temaLocal() || temaPC || 'grafite';
  document.documentElement.dataset.tema = tema;
  const meta = document.querySelector('meta[name="theme-color"]');
  const cor = getComputedStyle(document.documentElement)
    .getPropertyValue('--surface').trim();
  if (meta && cor) meta.content = cor;
}
$('temaLocal').value = temaLocal();
$('temaLocal').addEventListener('change', (e) => {
  try { localStorage.setItem('tema-local', e.target.value); } catch (err) { /* sem storage */ }
  aplicarTema();
});
aplicarTema();

let abaAtiva = 'chat';
function ativarAba(nome) {
  abaAtiva = nome;
  document.querySelectorAll('nav.tabs .tab').forEach(t =>
    t.classList.toggle('active', t.dataset.tab === nome));
  document.querySelectorAll('.page').forEach(p =>
    p.classList.toggle('active', p.id === 'page-' + nome));
  if (nome === 'projeto') carregarArvore('projeto');
  else if (nome === 'vault') carregarArvore('vault');
  else if (nome === 'chat') carregarChat();
  else if (nome === 'mais') carregarResumoPermissoes();
}
document.querySelectorAll('nav.tabs .tab').forEach(t =>
  t.addEventListener('click', () => ativarAba(t.dataset.tab)));

async function atualizarEstado() {
  try {
    const s = await get('/api/state');
    $('dot').classList.toggle('on', !!s.connected);
    $('badgeProjeto').textContent = s.project || '—';
    $('statusChat').innerHTML =
      'Projeto: <b>' + esc(s.project || '—') + '</b>' +
      ' · Status: <b>' + esc(s.status || '') + '</b>' +
      (s.agent_active ? ' · <b>agente rodando</b>' : '') +
      (s.queue ? ' · Fila: <b>' + s.queue + '</b>' : '');
    pintarEstado(s);
    pintarDecisoes(s.pending_decisions || []);
    pintarFila(s.queue_items || []);
    if (s.theme && s.theme !== temaPC) { temaPC = s.theme; aplicarTema(); }
  } catch (e) {
    $('statusChat').textContent = 'Sem conexão com o app.';
  }
}

function pintarEstado(s) {
  const el = $('estado');
  if (!el) return;
  el.innerHTML =
    '<div>Projeto: <b>' + esc(s.project || '—') + '</b></div>' +
    '<div>Status: <b>' + esc(s.status || '') + '</b></div>' +
    '<div>Conectado: <b>' + (s.connected ? 'sim' : 'não') + '</b></div>' +
    '<div>Agente: <b>' + (s.agent_active ? 'rodando' : 'parado') + '</b></div>' +
    '<div>Fila: <b>' + (s.queue || 0) + '</b></div>';
}

// ---------- decisões pendentes ----------
//
// O polling de `/api/state` roda a cada 2s. Se ele reconstruísse o card toda
// vez, o textarea de "Outra resposta…" seria destruído no meio da digitação.
// Duas defesas:
//
//   - `pintarDecisoes` só reconstrói se a LISTA mudou (assinatura JSON);
//     polling sem mudança não toca em nada.
//   - `reconstruirCardsDecisao` captura o estado (texto aberto + digitado +
//     imagens escolhidas) antes de remover e reaplica no fim.
//
// Cores: âmbar = recomendação do DeepSeek; verde = a escolha feita. Decisões
// já respondidas chegam pelo histórico do chat (`role: "decision"`) e ficam
// visíveis como card resolvido — PC e celular mostram a mesma coisa.

let decisoesAtuais = [];
let _assinaturaDecisoes = '';
let _estadoCardsDecisao = {};  // id -> {aberto, texto, arquivos: File[]}

function pintarDecisoes(lista) {
  decisoesAtuais = lista || [];
  const assinatura = JSON.stringify(decisoesAtuais);
  if (assinatura === _assinaturaDecisoes) return;
  _assinaturaDecisoes = assinatura;
  reconstruirCardsDecisao();
}

function _capturarEstadoCards() {
  const el = $('chatArea');
  if (!el) return;
  el.querySelectorAll('.decision.in-chat.pendente').forEach(card => {
    const id = card.dataset.id;
    if (!id) return;
    const area = card.querySelector('.decisao-livre');
    const input = card.querySelector('.decisao-livre-input');
    if (!area || !input) return;
    const anterior = _estadoCardsDecisao[id] || {};
    _estadoCardsDecisao[id] = {
      aberto: !area.hidden,
      texto: input.value || '',
      arquivos: anterior.arquivos || [],
    };
  });
}

function _rotuloOpcao(i, texto, recomendada) {
  const span = document.createElement('span');
  span.className = 'op-texto';
  span.textContent = (i + 1) + '. ' + texto;
  const frag = document.createDocumentFragment();
  frag.appendChild(span);
  if (recomendada) {
    const tag = document.createElement('span');
    tag.className = 'op-tag';
    tag.textContent = '★ recomendada';
    frag.appendChild(tag);
  }
  return frag;
}

function _linhaRecomendacao(d) {
  if (!d.recomendada) return '';
  return '<p class="rec">★ <b>Recomendação do DeepSeek:</b> opção '
    + esc(d.recomendada) + (d.motivo ? ' — ' + esc(d.motivo) : '') + '</p>';
}

// Card de decisão já resolvida (vem do histórico do chat).
function cardDecisaoResolvida(d) {
  const card = document.createElement('div');
  const cancelada = d.escolha == null;
  card.className = 'decision in-chat ' + (cancelada ? 'cancelada' : 'resolvida');
  const opcoes = d.opcoes || [];
  const livre = !cancelada && !opcoes.includes(d.escolha);
  const titulo = cancelada ? 'Decisão cancelada'
    : '✓ Decisão registrada' + (livre ? ' · resposta livre' : '');
  card.innerHTML = '<h3>' + esc(titulo) + '</h3>' +
    '<p class="pergunta">' + esc(d.pergunta) + '</p>' + _linhaRecomendacao(d);
  opcoes.forEach((op, i) => {
    const linha = document.createElement('div');
    linha.className = 'op';
    if (i + 1 === d.recomendada) linha.classList.add('reco');
    if (!cancelada && op === d.escolha) {
      linha.classList.add('escolhida');
      const ok = document.createElement('span');
      ok.className = 'op-check';
      ok.textContent = '✓';
      linha.appendChild(ok);
    }
    linha.appendChild(_rotuloOpcao(i, op, i + 1 === d.recomendada));
    card.appendChild(linha);
  });
  if (!cancelada) {
    const escolha = document.createElement('div');
    escolha.className = 'escolha-feita';
    escolha.innerHTML = '<b>Sua escolha:</b> ' + esc(d.escolha) +
      ((d.anexos || []).length
        ? '<br>📎 ' + esc(d.anexos.join(', ')) : '') +
      '<br><span class="origem">respondido pelo ' +
      esc(d.origem === 'celular' ? 'celular' : 'PC') + '</span>';
    card.appendChild(escolha);
    if (d.recomendada) {
      const recomendada = opcoes[d.recomendada - 1];
      const v = document.createElement('div');
      const segue = d.escolha === recomendada;
      v.className = 'veredito ' + (segue ? 'segue' : 'diverge');
      v.textContent = segue ? '★ Seguiu a recomendação do DeepSeek'
        : '↯ Diferente da recomendação (opção ' + d.recomendada + ')';
      card.appendChild(v);
    }
  }
  return card;
}

function _pintarChipsDecisao(barra, estado) {
  barra.innerHTML = '';
  const arquivos = estado.arquivos || [];
  barra.hidden = !arquivos.length;
  arquivos.forEach((f, idx) => {
    const chip = document.createElement('span');
    chip.className = 'anexo-chip';
    chip.innerHTML = '<span class="icone">🖼</span><span class="nome">' +
      esc(f.name || 'imagem') + '</span>';
    const x = document.createElement('button');
    x.type = 'button';
    x.className = 'chip-x';
    x.setAttribute('aria-label', 'Remover anexo');
    x.textContent = '✕';
    x.onclick = () => {
      estado.arquivos.splice(idx, 1);
      _pintarChipsDecisao(barra, estado);
    };
    chip.appendChild(x);
    barra.appendChild(chip);
  });
}

function reconstruirCardsDecisao(semAjuste) {
  const el = $('chatArea');
  const altura = el.scrollHeight, topo = el.scrollTop;
  _reconstruirCards();
  if (!semAjuste) aposMudarConteudo(altura, topo);
}

function _reconstruirCards() {
  const el = $('chatArea');
  if (!el) return;
  _capturarEstadoCards();
  el.querySelectorAll('.decision.in-chat.pendente').forEach(c => c.remove());
  if (!decisoesAtuais.length) return;

  for (const d of decisoesAtuais) {
    const estado = _estadoCardsDecisao[d.id] ||
      (_estadoCardsDecisao[d.id] = { aberto: false, texto: '', arquivos: [] });
    const card = document.createElement('div');
    card.className = 'decision in-chat pendente';
    card.dataset.id = d.id;
    card.innerHTML =
      '<h3>Decisão necessária</h3>' +
      '<p class="pergunta">' + esc(d.pergunta) + '</p>' + _linhaRecomendacao(d);
    (d.opcoes || []).forEach((op, i) => {
      const b = document.createElement('button');
      b.type = 'button';
      b.className = 'op';
      if (i + 1 === d.recomendada) b.classList.add('reco');
      b.appendChild(_rotuloOpcao(i, op, i + 1 === d.recomendada));
      b.onclick = () => responderDecisao(d.id, op, card, []);
      card.appendChild(b);
    });

    const outra = document.createElement('button');
    outra.type = 'button';
    outra.className = 'ghost decisao-outra';
    outra.textContent = '✎ Outra resposta…';
    card.appendChild(outra);

    const area = document.createElement('div');
    area.className = 'decisao-livre';
    area.hidden = true;

    const input = document.createElement('textarea');
    input.placeholder = 'Descreva sua decisão…';
    input.rows = 2;
    input.className = 'decisao-livre-input';
    area.appendChild(input);

    const barra = document.createElement('div');
    barra.className = 'anexos-bar';
    area.appendChild(barra);

    const arquivo = document.createElement('input');
    arquivo.type = 'file';
    arquivo.accept = 'image/*';
    arquivo.multiple = true;
    arquivo.hidden = true;
    area.appendChild(arquivo);

    const acoes = document.createElement('div');
    acoes.className = 'decisao-acoes';
    const imagem = document.createElement('button');
    imagem.type = 'button';
    imagem.className = 'ghost';
    imagem.textContent = '🖼 Imagem';
    const espaco = document.createElement('span');
    espaco.className = 'spacer';
    const cancelar = document.createElement('button');
    cancelar.type = 'button';
    cancelar.className = 'ghost';
    cancelar.textContent = 'Cancelar';
    const confirmar = document.createElement('button');
    confirmar.type = 'button';
    confirmar.className = 'primary';
    confirmar.textContent = 'Confirmar';
    acoes.append(imagem, espaco, cancelar, confirmar);
    area.appendChild(acoes);
    card.appendChild(area);

    outra.onclick = () => {
      area.hidden = false;
      outra.hidden = true;
      input.focus();
    };
    cancelar.onclick = () => {
      input.value = '';
      estado.arquivos = [];
      _pintarChipsDecisao(barra, estado);
      area.hidden = true;
      outra.hidden = false;
    };
    imagem.onclick = () => arquivo.click();
    arquivo.onchange = () => {
      estado.arquivos = (estado.arquivos || [])
        .concat(Array.from(arquivo.files || [])).slice(0, 8);
      arquivo.value = '';
      _pintarChipsDecisao(barra, estado);
    };
    input.addEventListener('paste', (e) => {
      const achados = arquivosDeDataTransfer(e.clipboardData)
        .filter(f => (f.type || '').startsWith('image/'));
      if (!achados.length) return;
      e.preventDefault();
      estado.arquivos = (estado.arquivos || []).concat(achados).slice(0, 8);
      _pintarChipsDecisao(barra, estado);
    });
    confirmar.onclick = () => {
      let texto = input.value.trim();
      const arquivos = estado.arquivos || [];
      if (!texto && arquivos.length) texto = 'Veja a imagem anexada.';
      if (!texto) return;
      responderDecisao(d.id, texto, card, arquivos);
    };

    if (estado.aberto) {
      area.hidden = false;
      outra.hidden = true;
      input.value = estado.texto || '';
    }
    _pintarChipsDecisao(barra, estado);

    el.appendChild(card);
  }
}

async function responderDecisao(id, escolha, card, arquivos) {
  card.querySelectorAll('button, textarea').forEach(e => e.disabled = true);
  try {
    const corpo = { escolha };
    if (arquivos && arquivos.length) {
      const anexos = [];
      for (const f of arquivos) {
        const b64 = await lerComoBase64(f);
        if (b64) anexos.push({
          rotulo: f.name || nomeParaTipo(f.type), tipo_mime: f.type || '',
          dados_b64: b64,
        });
      }
      corpo.anexos_json = anexos;
    }
    await post('/api/decision/' + encodeURIComponent(id), corpo);
    toast('Decisão enviada');
    decisoesAtuais = decisoesAtuais.filter(d => d.id !== id);
    _assinaturaDecisoes = JSON.stringify(decisoesAtuais);
    delete _estadoCardsDecisao[id];
    reconstruirCardsDecisao();
    setTimeout(carregarChat, 300);
  } catch (e) {
    card.querySelectorAll('button, textarea').forEach(el => el.disabled = false);
    toastErro(e);
  }
  atualizarEstado();
}

// ---------- fila de envio ----------
//
// Itens que esperam a vez no PC. ✕ cancela (a mensagem não é enviada e os
// anexos temporários são descartados lá).

let _assinaturaFila = '';
let _filaEditando = null;   // id do item com o editor aberto
let _filaUltima = [];
function pintarFila(itens) {
  const lista = itens || [];
  _filaUltima = lista;
  // Com um editor aberto, o polling não redesenha (perderia o que está
  // sendo digitado). Ao salvar/cancelar, redesenha com a lista mais nova.
  if (_filaEditando && lista.some(i => i.id === _filaEditando)) return;
  _filaEditando = null;
  const assinatura = JSON.stringify(lista);
  if (assinatura === _assinaturaFila) return;
  _assinaturaFila = assinatura;
  const box = $('filaEnvio');
  if (!box) return;
  box.hidden = !lista.length;
  const corpo = $('filaItens');
  $('filaTotal').textContent = lista.length;
  corpo.innerHTML = '';
  lista.forEach((item, i) => {
    const linha = document.createElement('div');
    linha.className = 'fila-item';
    const n = document.createElement('span');
    n.className = 'fila-n';
    n.textContent = i + 1;
    const texto = document.createElement('span');
    texto.className = 'fila-texto';
    texto.textContent = item.texto || '';
    texto.title = item.texto || '';
    const meta = document.createElement('span');
    meta.className = 'fila-meta';
    meta.textContent = ((item.anexos || []).length
      ? '📎' + item.anexos.length + ' · ' : '') + (item.agente ? 'Agente' : 'Chat');
    const x = document.createElement('button');
    x.type = 'button';
    x.className = 'fila-x';
    x.setAttribute('aria-label', 'Cancelar esta mensagem');
    x.textContent = '✕';
    x.onclick = () => cancelarFila(item.id, x);
    const ed = document.createElement('button');
    ed.type = 'button';
    ed.className = 'fila-x fila-ed';
    ed.setAttribute('aria-label', 'Editar esta mensagem');
    ed.textContent = '✎';
    ed.onclick = () => abrirEdicaoFila(item, linha);
    linha.append(n, texto, meta, ed, x);
    corpo.appendChild(linha);
  });
}

function abrirEdicaoFila(item, linha) {
  _filaEditando = item.id;
  const caixa = document.createElement('div');
  caixa.className = 'fila-edicao';
  const area = document.createElement('textarea');
  area.value = item.texto || '';
  area.rows = 3;
  area.setAttribute('aria-label', 'Texto da mensagem na fila');
  const acoes = document.createElement('div');
  acoes.className = 'decisao-acoes';
  const espaco = document.createElement('span');
  espaco.className = 'spacer';
  const cancelar = document.createElement('button');
  cancelar.type = 'button';
  cancelar.className = 'ghost';
  cancelar.textContent = 'Cancelar';
  const salvar = document.createElement('button');
  salvar.type = 'button';
  salvar.className = 'primary';
  salvar.textContent = 'Salvar';
  acoes.append(espaco, cancelar, salvar);
  caixa.append(area, acoes);
  linha.after(caixa);
  linha.hidden = true;
  area.focus();
  const fechar = () => {
    _filaEditando = null;
    _assinaturaFila = '';
    pintarFila(_filaUltima);
  };
  cancelar.onclick = fechar;
  salvar.onclick = async () => {
    const texto = area.value.trim();
    if (!texto) { toast('Texto vazio — para tirar da fila use ✕', true); return; }
    salvar.disabled = true;
    try {
      await post('/api/queue/edit', { id: item.id, texto });
      toast('Mensagem da fila editada');
    } catch (e) {
      toastErro(e);
    }
    fechar();
    atualizarEstado();
  };
}

async function cancelarFila(id, botao) {
  if (botao) botao.disabled = true;
  try {
    await post('/api/queue/cancel', { id });
    toast('Removida da fila');
  } catch (e) {
    toastErro(e);
    if (botao) botao.disabled = false;
  }
  atualizarEstado();
}

$('btnLimparFila').addEventListener('click', async () => {
  if (!confirm('Cancelar todas as mensagens da fila?')) return;
  try {
    const r = await post('/api/queue/clear');
    toast((r.cancelados || 0) + ' mensagem(ns) cancelada(s)');
  } catch (e) {
    toastErro(e);
  }
  atualizarEstado();
});

// ---------- chat ----------

// ---------- rolagem do chat ----------
//
// A lista acompanha a resposta enquanto você está no fim. Subir (dedo, roda
// do mouse) solta; nada te puxa de volta. Descer até o fim ou tocar no botão
// flutuante religa. Enquanto o dedo está na tela, nunca rolamos por conta
// própria. Rolagens nossas ficam marcadas em `ajustando` para o evento de
// scroll não confundir com a pessoa.

const chatEl = $('chatArea');
let seguirFim = true;
let novidade = false;
let ajustando = false;
let tocando = false;

function pertoDoFim() {
  return chatEl.scrollHeight - chatEl.scrollTop - chatEl.clientHeight < 80;
}

function rolarPara(topo) {
  ajustando = true;
  chatEl.scrollTop = topo;
  requestAnimationFrame(() => requestAnimationFrame(() => { ajustando = false; }));
}

function atualizarBotaoFim() {
  const longe = !pertoDoFim();
  if (!longe) novidade = false;
  const b = $('btnFim');
  b.hidden = !longe;
  b.classList.toggle('novidade', novidade);
  b.textContent = novidade ? '↓ Nova resposta' : '↓ Ir para o fim';
}

function irParaFim() {
  seguirFim = true;
  novidade = false;
  rolarPara(chatEl.scrollHeight);
  atualizarBotaoFim();
}

// Depois de mexer no conteúdo: acompanha, ou devolve você onde estava.
function aposMudarConteudo(alturaAntes, topoAntes) {
  if (seguirFim && !tocando) {
    rolarPara(chatEl.scrollHeight);
  } else {
    if (topoAntes != null && chatEl.scrollTop !== topoAntes) rolarPara(topoAntes);
    if (chatEl.scrollHeight > alturaAntes) novidade = true;
  }
  atualizarBotaoFim();
}

chatEl.addEventListener('scroll', () => {
  if (ajustando) return;
  seguirFim = pertoDoFim();
  atualizarBotaoFim();
}, { passive: true });
chatEl.addEventListener('wheel', (e) => {
  if (e.deltaY < 0) seguirFim = false;
}, { passive: true });
chatEl.addEventListener('touchstart', () => { tocando = true; }, { passive: true });
const soltarToque = () => {
  tocando = false;
  seguirFim = pertoDoFim();
  atualizarBotaoFim();
};
chatEl.addEventListener('touchend', soltarToque, { passive: true });
chatEl.addEventListener('touchcancel', soltarToque, { passive: true });
$('btnFim').addEventListener('click', irParaFim);

// Streaming muda a cada poll: só o balão em curso é redesenhado, o resto
// do chat (e o que você está lendo) fica intacto.
function pintarStreaming(el, texto) {
  let div = el.querySelector('.msg.streaming');
  if (texto == null) {
    if (div) div.remove();
    return;
  }
  if (!div) {
    div = document.createElement('div');
    div.className = 'msg assistant streaming';
    el.insertBefore(div, el.querySelector('.decision.in-chat.pendente'));
  }
  div.innerHTML = md(texto);
}

let ultimoChat = '';
let ultimasMensagens = '';
async function carregarChat() {
  try {
    const dados = await get('/api/chat');
    const assinatura = JSON.stringify(dados);
    if (assinatura === ultimoChat) return;
    ultimoChat = assinatura;
    const el = chatEl;
    const altura = el.scrollHeight, topo = el.scrollTop;
    const mensagens = JSON.stringify(dados.messages || []);
    if (mensagens === ultimasMensagens) {
      pintarStreaming(el, dados.streaming);
      aposMudarConteudo(altura, topo);
      return;
    }
    ultimasMensagens = mensagens;
    el.innerHTML = '';
    (dados.messages || []).forEach(m => {
      if (m.role === 'decision' && m.decision) {
        el.appendChild(cardDecisaoResolvida(m.decision));
        return;
      }
      const div = document.createElement('div');
      div.className = 'msg ' + (m.role === 'user' ? 'user'
                                : m.role === 'system' ? 'system'
                                : 'assistant');
      div.innerHTML = m.role === 'system' ? esc(m.content) : md(m.content);
      el.appendChild(div);
    });
    pintarStreaming(el, dados.streaming);
    reconstruirCardsDecisao(true);
    aposMudarConteudo(altura, topo);
  } catch (e) {
    // silencioso — o polling tenta de novo
  }
}

async function enviar() {
  const entrada = $('entrada');
  const texto = entrada.value.trim();
  if (!texto) return;
  const btn = $('btnEnviar');
  btn.disabled = true;
  try {
    await post('/api/send', {
      texto,
      agente: $('modoAgente').checked,
    });
    entrada.value = '';
    toast('Enviado');
    irParaFim();
    pintarAnexos([]);
    setTimeout(carregarChat, 400);
  } catch (e) {
    toastErro(e);
  } finally {
    btn.disabled = false;
  }
}
$('btnEnviar').addEventListener('click', enviar);
$('entrada').addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); enviar(); }
});

async function novoChat() {
  const btn = $('btnNovoChat');
  if (btn.disabled) return;
  if (!confirm('Iniciar uma nova conversa no DeepSeek? A conversa atual ' +
               'continua arquivada lá.')) {
    return;
  }
  btn.disabled = true;
  const original = btn.textContent;
  btn.textContent = '…';
  try {
    const r = await post('/api/new-chat');
    if (r.erro) throw new Error(r.erro);
    toast('Abrindo nova conversa…');
    setTimeout(carregarChat, 900);
    setTimeout(atualizarEstado, 1200);
  } catch (e) {
    toastErro(e);
  } finally {
    btn.textContent = original;
    setTimeout(() => { btn.disabled = false; }, 1500);
  }
}
$('btnNovoChat').addEventListener('click', novoChat);

function lerComoBase64(file) {
  return new Promise((resolve, reject) => {
    const leitor = new FileReader();
    leitor.onload = () => {
      const url = String(leitor.result || '');
      const virgula = url.indexOf(',');
      resolve(virgula >= 0 ? url.slice(virgula + 1) : '');
    };
    leitor.onerror = () => reject(leitor.error || new Error('falha ao ler'));
    leitor.readAsDataURL(file);
  });
}

function nomeParaTipo(tipo) {
  const ext = (tipo || '').split('/')[1] || 'bin';
  const limpo = ext.split('+')[0].replace(/[^a-z0-9]/gi, '') || 'bin';
  return 'colado-' + Date.now() + '-' + Math.floor(Math.random() * 1000) + '.' + limpo;
}

async function anexarArquivos(files) {
  const lista = Array.from(files || []);
  if (!lista.length) return;
  const btn = $('btnAnexar');
  const btnCol = $('btnColar');
  btn.disabled = true;
  if (btnCol) btnCol.disabled = true;
  try {
    const anexos = [];
    for (const f of lista.slice(0, 8)) {
      const tipo = f.type || '';
      const nome = f.name || nomeParaTipo(tipo);
      const b64 = await lerComoBase64(f);
      if (!b64) continue;
      anexos.push({ rotulo: nome, tipo_mime: tipo, dados_b64: b64 });
    }
    if (!anexos.length) { toast('Nada para anexar', true); return; }
    const r = await post('/api/attach', { anexos_json: anexos });
    const nomes = (r.adicionados || []).map(a => a.rotulo).join(', ');
    toast('Anexado: ' + nomes);
    await atualizarAnexos();
  } catch (e) {
    toastErro(e, 'Falha ao anexar: ');
  } finally {
    btn.disabled = false;
    if (btnCol) btnCol.disabled = false;
    $('arquivoInput').value = '';
  }
}

function pintarAnexos(anexos) {
  const bar = $('barraAnexos');
  if (!bar) return;
  if (!anexos.length) {
    bar.hidden = true;
    bar.innerHTML = '';
    return;
  }
  bar.hidden = false;
  bar.innerHTML = '';
  for (const a of anexos) {
    const chip = document.createElement('span');
    chip.className = 'anexo-chip';
    const icone = a.modo === 'upload' ? '🖼' : '📄';
    chip.innerHTML = '<span class="icone">' + icone +
                     '</span><span class="nome">' + esc(a.rotulo) + '</span>';
    bar.appendChild(chip);
  }
}

async function atualizarAnexos() {
  try {
    const r = await get('/api/attachments');
    pintarAnexos(r.anexos || []);
  } catch (e) { /* silencioso */ }
}

$('btnAnexar').addEventListener('click', () => $('arquivoInput').click());
$('arquivoInput').addEventListener('change', (e) => anexarArquivos(e.target.files));

function arquivosDeDataTransfer(dt) {
  if (!dt) return [];
  const achados = [];
  const vistos = new Set();
  const adicionar = (f) => {
    if (!f) return;
    const chave = (f.name || '') + '::' + (f.size || 0) + '::' + (f.type || '');
    if (vistos.has(chave)) return;
    vistos.add(chave);
    achados.push(f);
  };
  if (dt.items) for (const item of dt.items) {
    if (item.kind === 'file') adicionar(item.getAsFile());
  }
  if (dt.files) for (const f of dt.files) adicionar(f);
  return achados;
}

$('entrada').addEventListener('paste', (e) => {
  const dt = e.clipboardData;
  if (!dt) return;
  const arquivos = arquivosDeDataTransfer(dt);
  if (!arquivos.length) return;
  e.preventDefault();
  anexarArquivos(arquivos);
});

async function colar() {
  if (!navigator.clipboard || !navigator.clipboard.read) {
    toast('Este navegador não permite ler a área de transferência. Use Anexar.', true);
    return;
  }
  const btn = $('btnColar');
  btn.disabled = true;
  try {
    const itens = await navigator.clipboard.read();
    const arquivos = [];
    for (const item of itens) {
      const tiposImagem = item.types.filter(t => t.startsWith('image/'));
      const tipos = tiposImagem.length ? tiposImagem : item.types;
      for (const tipo of tipos) {
        try {
          const blob = await item.getType(tipo);
          if (!blob || !blob.size) continue;
          arquivos.push(new File([blob], nomeParaTipo(tipo), { type: tipo }));
        } catch (err) { /* tipo indisponível — segue */ }
      }
    }
    if (!arquivos.length) {
      toast('Nada de imagem ou arquivo na área de transferência.', true);
      return;
    }
    await anexarArquivos(arquivos);
  } catch (e) {
    toastErro(e, 'Não consegui ler a área de transferência: ');
  } finally {
    btn.disabled = false;
  }
}
$('btnColar').addEventListener('click', colar);

async function carregarArvore(tipo) {
  const alvo = tipo === 'projeto' ? $('treeProjeto') : $('treeVault');
  const caminho = tipo === 'projeto' ? $('caminhoProjeto') : $('caminhoVault');
  alvo.innerHTML = '<div class="vazio">Carregando…</div>';
  try {
    const dados = await post('/api/tree', { tipo });
    if (dados.erro) {
      alvo.innerHTML = '<div class="vazio">' + esc(dados.erro) + '</div>';
      return;
    }
    caminho.textContent = tipo === 'projeto'
      ? 'projeto: ' + (await get('/api/projects')).nome_atual || '—'
      : 'vault: ' + ((await get('/api/vaults')).vinculado || '—');
    renderArvore(alvo, tipo, dados.entries || [], '');
  } catch (e) {
    if (e && e.message === 'app_ocupado') {
      alvo.innerHTML = '<div class="vazio">App ocupado no PC. ' +
                       esc(e.dica || 'Tente de novo.') + '</div>';
    } else {
      alvo.innerHTML = '<div class="vazio">' + esc(e.message) + '</div>';
    }
  }
}

function renderArvore(el, tipo, entries, prefixo) {
  el.innerHTML = '';
  if (!entries.length) {
    el.innerHTML = '<div class="vazio">Pasta vazia.</div>';
    return;
  }
  const diretos = new Map();
  const base = prefixo ? prefixo + '/' : '';
  for (const e of entries) {
    if (!e.path.startsWith(base)) continue;
    const resto = e.path.slice(base.length);
    const primeiro = resto.split('/')[0];
    if (!primeiro) continue;
    const filhoCaminho = base + primeiro;
    if (!diretos.has(filhoCaminho)) {
      diretos.set(filhoCaminho, {
        nome: primeiro,
        caminho: filhoCaminho,
        is_dir: e.is_dir || resto.includes('/'),
      });
    }
  }
  const lista = Array.from(diretos.values()).sort((a, b) =>
    (a.is_dir === b.is_dir) ? a.nome.localeCompare(b.nome) : (a.is_dir ? -1 : 1));
  for (const item of lista) {
    const div = document.createElement('div');
    div.className = 'item ' + (item.is_dir ? 'dir' : 'file');
    div.innerHTML = '<span class="ico">' + (item.is_dir ? '📁' : '📄') +
                    '</span><span class="nome">' + esc(item.nome) + '</span>';
    div.onclick = () => {
      if (item.is_dir) renderArvore(el, tipo, entries, item.caminho);
      else abrirArquivo(tipo, item.caminho);
    };
    el.appendChild(div);
  }
  if (prefixo) {
    const up = document.createElement('div');
    up.className = 'item dir';
    up.innerHTML = '<span class="ico">↩</span><span class="nome">voltar</span>';
    up.onclick = () => {
      const pai = prefixo.split('/').slice(0, -1).join('/');
      renderArvore(el, tipo, entries, pai);
    };
    el.insertBefore(up, el.firstChild);
  }
}

let arquivoAtual = null;
async function abrirArquivo(tipo, caminho) {
  try {
    const dados = await post('/api/read-file', { tipo, caminho });
    if (dados.erro) { toast(dados.erro, true); return; }
    arquivoAtual = { tipo, caminho };
    $('dlgArquivoTitulo').textContent = caminho.split('/').pop();
    $('dlgArquivoCaminho').textContent = (tipo === 'vault' ? 'vault/' : '') + caminho;
    $('dlgArquivoTexto').value = dados.conteudo || '';
    $('dlgArquivo').showModal();
  } catch (e) {
    toastErro(e);
  }
}

$('btnFecharArquivo').addEventListener('click', (e) => {
  e.preventDefault();
  $('dlgArquivo').close();
  arquivoAtual = null;
});

$('btnSalvarArquivo').addEventListener('click', async () => {
  if (!arquivoAtual) return;
  try {
    const r = await post('/api/write-file', {
      tipo: arquivoAtual.tipo,
      caminho: arquivoAtual.caminho,
      conteudo: $('dlgArquivoTexto').value,
      criar: false,
    });
    if (r.erro) throw new Error(r.erro);
    toast('Salvo ✓');
    $('dlgArquivo').close();
    arquivoAtual = null;
    carregarArvore(abaAtiva === 'vault' ? 'vault' : 'projeto');
  } catch (e) {
    toastErro(e);
  }
});

$('btnApagarArquivo').addEventListener('click', async () => {
  if (!arquivoAtual) return;
  if (!confirm('Apagar ' + arquivoAtual.caminho + '?')) return;
  try {
    const r = await post('/api/delete-file', {
      tipo: arquivoAtual.tipo, caminho: arquivoAtual.caminho });
    if (r.erro) throw new Error(r.erro);
    toast('Apagado (backup mantido)');
    $('dlgArquivo').close();
    arquivoAtual = null;
    carregarArvore(abaAtiva === 'vault' ? 'vault' : 'projeto');
  } catch (e) {
    toastErro(e);
  }
});

let alvoPasta = null;

async function abrirDialogoPasta(tipo) {
  alvoPasta = { tipo, caminho: '' };
  $('dlgPastaTitulo').textContent =
    tipo === 'projeto' ? 'Escolher projeto' :
    tipo === 'vault' ? 'Escolher vault' :
    tipo === 'grant' ? 'Adicionar pasta autorizada' : 'Escolher pasta';
  await navegarPasta('');
  $('dlgPasta').showModal();
}

async function navegarPasta(caminho) {
  try {
    const dados = await post('/api/browse', { caminho });
    if (dados.erro) { toast(dados.erro, true); return; }
    alvoPasta.caminho = dados.atual;
    alvoPasta.pai = dados.pai;
    $('dlgPastaAtual').textContent = dados.atual;
    const lista = $('dlgPastaLista');
    lista.innerHTML = '';
    if (!dados.filhos.length) {
      lista.innerHTML = '<div class="vazio">Nenhuma subpasta.</div>';
    }
    for (const f of dados.filhos) {
      const div = document.createElement('div');
      div.className = 'item dir';
      div.innerHTML = '<span class="ico">📁</span><span class="nome">' +
                      esc(f.nome) + '</span>';
      div.onclick = () => navegarPasta(f.caminho);
      lista.appendChild(div);
    }
  } catch (e) {
    toastErro(e);
  }
}

$('btnTrocarProjeto').addEventListener('click', () => abrirDialogoPasta('projeto'));
$('btnTrocarVault').addEventListener('click', () => abrirDialogoPasta('vault'));
$('btnFecharPasta').addEventListener('click', () => $('dlgPasta').close());
$('btnPastaPai').addEventListener('click', () => {
  if (alvoPasta && alvoPasta.pai) navegarPasta(alvoPasta.pai);
});
$('btnEscolherPasta').addEventListener('click', async () => {
  if (!alvoPasta) return;
  if (alvoPasta.tipo === 'grant') {
    const caminho = alvoPasta.caminho;
    if (!caminho) return;
    if (permGrantsState.some(g => g.path === caminho)) {
      toast('Pasta já autorizada', true);
      $('dlgPasta').close();
      return;
    }
    permGrantsState.push({
      path: caminho, read: true, create: false, edit: false, delete: false,
    });
    renderGrants(permGrantsState);
    $('dlgPasta').close();
    return;
  }
  try {
    const rota = alvoPasta.tipo === 'projeto' ? '/api/open-project' : '/api/open-vault';
    const r = await post(rota, { caminho: alvoPasta.caminho });
    if (r.erro) throw new Error(r.erro);
    toast(alvoPasta.tipo === 'projeto' ? 'Projeto aberto' : 'Vault vinculado');
    $('dlgPasta').close();
    atualizarEstado();
    if (alvoPasta.tipo === 'projeto') carregarArvore('projeto');
    else carregarArvore('vault');
  } catch (e) {
    toastErro(e);
  }
});

let novoTipo = 'projeto';
let novoPai = '';
function abrirNovo(tipo, pai) {
  novoTipo = tipo;
  novoPai = pai || '';
  $('novoOnde').textContent = (tipo === 'vault' ? 'vault/' : '') + (pai || '.');
  $('novoNome').value = '';
  $('dlgNovo').showModal();
}

$('btnFecharNovo').addEventListener('click', () => $('dlgNovo').close());
$('btnCriarPasta').addEventListener('click', async () => {
  const nome = $('novoNome').value.trim();
  if (!nome) return;
  try {
    const r = await post('/api/new-folder', {
      tipo: novoTipo, caminho: (novoPai + '/' + nome).replace(/^\/+/, ''),
    });
    if (r.erro) throw new Error(r.erro);
    toast('Pasta criada ✓');
    $('dlgNovo').close();
    carregarArvore(novoTipo);
  } catch (e) { toastErro(e); }
});
$('btnCriarArquivo').addEventListener('click', async () => {
  const nome = $('novoNome').value.trim();
  if (!nome) return;
  try {
    const r = await post('/api/write-file', {
      tipo: novoTipo,
      caminho: (novoPai + '/' + nome).replace(/^\/+/, ''),
      conteudo: '',
      criar: true,
    });
    if (r.erro) throw new Error(r.erro);
    toast('Arquivo criado ✓');
    $('dlgNovo').close();
    carregarArvore(novoTipo);
  } catch (e) { toastErro(e); }
});

// ---------- permissões ----------

let permGrantsState = [];

const ROTULOS_MODO = {
  project_confirm: 'Projeto (confirmar cada ação)',
  project_auto: 'Projeto + vault (automático)',
  folders: 'Pastas escolhidas',
  computer_confirm: 'Computador (confirmar)',
  computer_auto: 'Computador (automático)',
};

async function carregarResumoPermissoes() {
  const el = $('permResumo');
  if (!el) return;
  try {
    const r = await get('/api/permissions');
    if (r.erro) { el.textContent = r.erro; return; }
    const leitura = r.confirm_reads ? 'confirma leitura' : 'leitura automática';
    const n = (r.grants || []).length;
    el.textContent = (ROTULOS_MODO[r.mode] || r.mode) +
      ' · ' + leitura + ' · ' + n + ' pasta(s)';
  } catch (e) {
    el.textContent = 'Sem conexão com o app.';
  }
}

function _opCheckbox(key, rotulo, marcado) {
  const label = document.createElement('label');
  label.style.cssText = 'display:inline-flex;align-items:center;gap:6px;' +
                        'margin-right:10px;font-size:13px';
  const inp = document.createElement('input');
  inp.type = 'checkbox';
  inp.dataset.key = key;
  inp.checked = !!marcado;
  label.appendChild(inp);
  label.appendChild(document.createTextNode(rotulo));
  return label;
}

function renderGrants(grants) {
  const box = $('permGrants');
  if (!box) return;
  box.innerHTML = '';
  if (!grants.length) {
    box.innerHTML = '<div class="vazio">Nenhuma pasta autorizada.</div>';
    return;
  }
  grants.forEach((g, idx) => {
    const row = document.createElement('div');
    row.dataset.idx = String(idx);
    row.style.cssText = 'padding:8px;margin:6px 0;border:1px solid ' +
                        'rgba(255,255,255,.12);border-radius:8px';

    const caminho = document.createElement('div');
    caminho.className = 'small';
    caminho.style.cssText = 'word-break:break-all;margin-bottom:6px';
    caminho.textContent = g.path;
    row.appendChild(caminho);

    const ops = document.createElement('div');
    ops.style.cssText = 'display:flex;flex-wrap:wrap;align-items:center';
    ops.appendChild(_opCheckbox('read', 'Ler', g.read));
    ops.appendChild(_opCheckbox('create', 'Criar', g.create));
    ops.appendChild(_opCheckbox('edit', 'Editar', g.edit));
    ops.appendChild(_opCheckbox('delete', 'Apagar', g.delete));

    const remover = document.createElement('button');
    remover.type = 'button';
    remover.className = 'ghost';
    remover.style.marginLeft = 'auto';
    remover.textContent = '✕';
    remover.title = 'Remover esta pasta';
    remover.onclick = () => {
      permGrantsState.splice(idx, 1);
      renderGrants(permGrantsState);
    };
    ops.appendChild(remover);

    row.appendChild(ops);
    box.appendChild(row);
  });

  box.querySelectorAll('input[type=checkbox]').forEach(inp => {
    inp.addEventListener('change', () => {
      const row = inp.closest('div[data-idx]');
      if (!row) return;
      const idx = Number(row.dataset.idx);
      const key = inp.dataset.key;
      if (permGrantsState[idx]) {
        permGrantsState[idx][key] = inp.checked;
      }
    });
  });
}

async function abrirPermissoes() {
  try {
    const r = await get('/api/permissions');
    if (r.erro) { toast(r.erro, true); return; }
    permGrantsState = (r.grants || []).map(g => ({
      path: g.path,
      read: !!g.read, create: !!g.create,
      edit: !!g.edit, delete: !!g.delete,
    }));

    const sel = $('permMode');
    sel.innerHTML = '';
    const modos = r.modos && r.modos.length
      ? r.modos
      : ['project_confirm', 'project_auto', 'folders',
         'computer_confirm', 'computer_auto'];
    for (const m of modos) {
      const opt = document.createElement('option');
      opt.value = m;
      opt.textContent = ROTULOS_MODO[m] || m;
      if (m === r.mode) opt.selected = true;
      sel.appendChild(opt);
    }
    $('permConfirmReads').checked = !!r.confirm_reads;
    _atualizarEstadoConfirmReads();
    renderGrants(permGrantsState);
    $('dlgPermissoes').showModal();
  } catch (e) {
    toastErro(e);
  }
}

function _atualizarEstadoConfirmReads() {
  const modo = $('permMode').value;
  // Espelha o desktop: em `project_auto` as leituras são sempre automáticas.
  const chk = $('permConfirmReads');
  if (modo === 'project_auto') {
    chk.checked = false;
    chk.disabled = true;
  } else {
    chk.disabled = false;
  }
}

$('btnAbrirPermissoes').addEventListener('click', abrirPermissoes);
$('btnFecharPermissoes').addEventListener('click', () => $('dlgPermissoes').close());
$('permMode').addEventListener('change', _atualizarEstadoConfirmReads);
$('btnPermAddPasta').addEventListener('click', () => abrirDialogoPasta('grant'));
$('btnSalvarPermissoes').addEventListener('click', async () => {
  try {
    const r = await post('/api/permissions', {
      mode: $('permMode').value,
      grants: permGrantsState,
      confirm_reads: $('permConfirmReads').checked,
    });
    if (r.erro) throw new Error(r.erro);
    toast('Permissões salvas ✓');
    $('dlgPermissoes').close();
    carregarResumoPermissoes();
  } catch (e) {
    toastErro(e);
  }
});

function urlBase64ToUint8Array(base64) {
  const padding = '='.repeat((4 - base64.length % 4) % 4);
  const b64 = (base64 + padding).replace(/-/g, '+').replace(/_/g, '/');
  const raw = atob(b64);
  const out = new Uint8Array(raw.length);
  for (let i = 0; i < raw.length; i++) out[i] = raw.charCodeAt(i);
  return out;
}

async function inscreverNotificacoes() {
  const body = $('notifBody');
  try {
    const reg = await navigator.serviceWorker.register('/sw.js');
    await navigator.serviceWorker.ready;
    const perm = await Notification.requestPermission();
    if (perm !== 'granted') {
      body.textContent = 'Permissão negada. Ative nas configurações do navegador.';
      return;
    }
    const keyResp = await fetch('/api/vapid-public-key',
                                { credentials: 'same-origin' });
    if (!keyResp.ok) { body.textContent = 'App não devolveu a chave VAPID.'; return; }
    const { key } = await keyResp.json();
    const sub = await reg.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: urlBase64ToUint8Array(key),
    });
    await post('/api/subscribe', sub.toJSON());
    body.textContent = 'Notificações ativas ✓';
  } catch (e) {
    body.textContent = 'Erro: ' + String(e);
  }
}

async function montarNotificacoes() {
  const body = $('notifBody');
  const isIos = /iPad|iPhone|iPod/.test(navigator.userAgent)
                || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
  const standalone = window.navigator.standalone === true
                     || window.matchMedia('(display-mode: standalone)').matches;
  if (isIos && !standalone) {
    body.innerHTML =
      'No iPhone, notificações só funcionam com o painel adicionado à Tela de ' +
      'Início. Toque em <b>Compartilhar</b> → <b>Adicionar à Tela de Início</b>, ' +
      'abra pelo ícone criado e volte aqui para ativar.';
    return;
  }
  if (!('serviceWorker' in navigator) || !('PushManager' in window)) {
    body.textContent = 'Este navegador não suporta notificações push.';
    return;
  }
  try {
    const reg = await navigator.serviceWorker.getRegistration();
    const sub = reg && await reg.pushManager.getSubscription();
    if (sub) { body.textContent = 'Notificações ativas ✓'; return; }
  } catch (e) { /* segue */ }
  body.innerHTML = '<button class="primary" id="btnNotif">Ativar notificações</button>';
  $('btnNotif').onclick = inscreverNotificacoes;
}

atualizarEstado();
carregarChat();
carregarResumoPermissoes();
atualizarAnexos();
montarNotificacoes();
setInterval(atualizarEstado, 2000);
setInterval(() => { if (abaAtiva === 'chat') carregarChat(); }, 1500);
setInterval(atualizarAnexos, 3000);
