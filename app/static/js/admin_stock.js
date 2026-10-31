/*
  Admin -> Gestao de estoque (Fase 6).

  Regras obedecidas:
  - Nunca innerHTML com dado do servidor (textContent / createElement).
  - CSRF via header X-CSRF-Token lido do cookie em toda rota mutante.
  - Qty em UN => inteiro; KG/L => 3 casas decimais.
*/

(function () {
  'use strict';

  const API_ENTRADA = '/api/admin/stock/entry';
  const API_PERDA = '/api/admin/stock/loss';
  const API_AJUSTE = '/api/admin/stock/adjustment';
  const API_HISTORICO = '/api/admin/stock/movements';
  const API_BYCODE = '/api/products/by-code/';
  const API_SEARCH = '/api/products/search';

  const TYPE_LABEL = {
    entrada: 'Entrada',
    venda: 'Venda',
    ajuste: 'Ajuste',
    perda: 'Perda',
    estorno: 'Estorno',
  };

  // ---------- helpers ----------

  function readCookie(name) {
    const pairs = document.cookie ? document.cookie.split(';') : [];
    for (let i = 0; i < pairs.length; i++) {
      const kv = pairs[i].trim().split('=');
      if (kv[0] === name) return decodeURIComponent(kv.slice(1).join('='));
    }
    return '';
  }

  async function apiFetch(path, options) {
    const opts = Object.assign({}, options || {});
    opts.headers = Object.assign({
      'Content-Type': 'application/json',
      'Accept': 'application/json',
    }, opts.headers || {});
    const method = (opts.method || 'GET').toUpperCase();
    if (method !== 'GET') {
      opts.headers['X-CSRF-Token'] = readCookie('csrf_token');
    }
    const resp = await fetch(path, opts);
    if (resp.status === 401) {
      window.location.assign('/login');
      throw new Error('Nao autenticado.');
    }
    const ct = resp.headers.get('content-type') || '';
    const body = ct.indexOf('application/json') >= 0
      ? await resp.json() : await resp.text();
    if (!resp.ok) {
      let msg = (body && body.detail) || resp.statusText || 'Erro.';
      if (body && Array.isArray(body.errors)) {
        msg = msg + ' ' + body.errors.map(e => e.msg || '').join('; ');
      }
      throw new Error(msg);
    }
    return body;
  }

  function clearNode(el) {
    while (el.firstChild) el.removeChild(el.firstChild);
  }

  function showError(id, msg) {
    const el = document.getElementById(id);
    if (!el) return;
    if (!msg) { el.hidden = true; el.textContent = ''; return; }
    el.hidden = false;
    el.textContent = msg;
  }

  function showFeedback(msg, kind) {
    const el = document.getElementById('feedback');
    clearNode(el);
    el.className = 'feedback';
    if (!msg) return;
    el.classList.add(kind === 'ok' ? 'ok' : 'erro');
    el.textContent = msg;
    setTimeout(() => {
      if (el.textContent === msg) {
        clearNode(el);
        el.className = 'feedback';
      }
    }, 4000);
  }

  // qty_milli (int) -> string formatada
  function formatQty(milli, unit) {
    const sign = milli < 0 ? '-' : '';
    const abs = Math.abs(milli | 0);
    if (unit === 'UN') {
      if (abs % 1000 === 0) return sign + String(abs / 1000);
      const inteiro = Math.floor(abs / 1000);
      const resto = (abs % 1000).toString().padStart(3, '0');
      return sign + inteiro + ',' + resto;
    }
    const inteiro = Math.floor(abs / 1000);
    const resto = (abs % 1000).toString().padStart(3, '0');
    return sign + inteiro + ',' + resto;
  }

  // string -> qty_milli (int). Lanca Error em caso de formato invalido.
  function parseQty(text, unit) {
    if (text == null) throw new Error('Quantidade vazia.');
    let cleaned = String(text).trim().replace('.', ',');
    if (!cleaned) throw new Error('Quantidade vazia.');
    if (cleaned.charAt(0) === '-') throw new Error('Quantidade negativa nao e aceita.');
    let integerPart = cleaned;
    let decimalPart = '';
    if (cleaned.indexOf(',') >= 0) {
      const parts = cleaned.split(',');
      integerPart = parts[0] || '0';
      decimalPart = parts.slice(1).join('');
    }
    if (!/^\d+$/.test(integerPart)) throw new Error('Parte inteira invalida.');
    if (decimalPart && !/^\d+$/.test(decimalPart)) throw new Error('Parte decimal invalida.');
    if (decimalPart.length > 3) throw new Error('Mais de 3 casas decimais.');
    decimalPart = (decimalPart || '').padEnd(3, '0');
    const milli = parseInt(integerPart, 10) * 1000 + parseInt(decimalPart || '0', 10);
    if (!isFinite(milli) || milli <= 0) throw new Error('Quantidade invalida.');
    return milli;
  }

  // ---------- resolucao de produto ----------

  async function resolveProductByCode(code) {
    // Primeiro tenta o endpoint rapido de PDV
    try {
      const r = await apiFetch(API_BYCODE + encodeURIComponent(code));
      return r.product;
    } catch (_) {
      // Se nao resolveu por codigo, tenta busca por nome
    }
    const resp = await apiFetch(API_SEARCH + '?q=' + encodeURIComponent(code));
    if (!Array.isArray(resp) || resp.length === 0) {
      throw new Error('Produto nao encontrado.');
    }
    return resp[0];
  }

  function fillProductBox(prefix, product) {
    document.getElementById(prefix + '-selecionado').hidden = false;
    document.getElementById(prefix + '-nome').textContent =
      product.name + ' (' + product.unit + ')';
    document.getElementById(prefix + '-saldo').textContent =
      formatQty(product.stock_milli, product.unit);
    document.getElementById(prefix + '-product-id').value = String(product.id);
    const codeField = document.getElementById(prefix + '-code');
    if (codeField) codeField.dataset.unit = product.unit;
  }

  function clearProductBox(prefix) {
    document.getElementById(prefix + '-selecionado').hidden = true;
    document.getElementById(prefix + '-product-id').value = '';
    const codeField = document.getElementById(prefix + '-code');
    if (codeField) codeField.dataset.unit = '';
  }

  function bindProductLookup(prefix) {
    const field = document.getElementById(prefix + '-code');
    field.addEventListener('change', async () => {
      const code = field.value.trim();
      clearProductBox(prefix);
      showError(prefix + '-erro', null);
      if (!code) return;
      try {
        const product = await resolveProductByCode(code);
        fillProductBox(prefix, product);
        // Para ajuste: atualiza delta previsto
        if (prefix === 'ajuste') updateDeltaPreview();
      } catch (err) {
        showError(prefix + '-erro', err.message);
      }
    });
  }

  // ---------- entrada ----------

  async function submitEntrada(ev) {
    ev.preventDefault();
    showError('entrada-erro', null);
    const productId = parseInt(document.getElementById('entrada-product-id').value, 10);
    const unit = document.getElementById('entrada-code').dataset.unit || 'UN';
    const qtyText = document.getElementById('entrada-qty').value;
    const reason = document.getElementById('entrada-reason').value.trim();

    if (!productId) {
      showError('entrada-erro', 'Selecione um produto valido.');
      return;
    }
    let qty_milli;
    try { qty_milli = parseQty(qtyText, unit); }
    catch (err) { showError('entrada-erro', err.message); return; }

    const payload = { product_id: productId, qty_milli: qty_milli };
    if (reason) payload.reason = reason;

    try {
      await apiFetch(API_ENTRADA, { method: 'POST', body: JSON.stringify(payload) });
      showFeedback('Entrada registrada.', 'ok');
      document.getElementById('form-entrada').reset();
      clearProductBox('entrada');
    } catch (err) {
      showError('entrada-erro', err.message);
    }
  }

  // ---------- perda ----------

  async function submitPerda(ev) {
    ev.preventDefault();
    showError('perda-erro', null);
    const productId = parseInt(document.getElementById('perda-product-id').value, 10);
    const unit = document.getElementById('perda-code').dataset.unit || 'UN';
    const qtyText = document.getElementById('perda-qty').value;
    const reason = document.getElementById('perda-reason').value.trim();

    if (!productId) { showError('perda-erro', 'Selecione um produto valido.'); return; }
    if (reason.length < 3) { showError('perda-erro', 'Motivo obrigatorio (min 3 caracteres).'); return; }
    let qty_milli;
    try { qty_milli = parseQty(qtyText, unit); }
    catch (err) { showError('perda-erro', err.message); return; }

    try {
      await apiFetch(API_PERDA, {
        method: 'POST',
        body: JSON.stringify({ product_id: productId, qty_milli: qty_milli, reason: reason }),
      });
      showFeedback('Perda registrada.', 'ok');
      document.getElementById('form-perda').reset();
      clearProductBox('perda');
    } catch (err) {
      showError('perda-erro', err.message);
    }
  }

  // ---------- ajuste ----------

  function updateDeltaPreview() {
    const saldoText = document.getElementById('ajuste-saldo').textContent;
    const novoText = document.getElementById('ajuste-novo').value;
    const unit = document.getElementById('ajuste-code').dataset.unit || 'UN';
    const target = document.getElementById('ajuste-delta');
    if (!saldoText || !novoText) { target.textContent = '—'; return; }
    try {
      // saldoText pode ter sinal; recompor:
      const atualMilli = parseSignedQty(saldoText, unit);
      const novoMilli = parseQty(novoText, unit);
      const delta = novoMilli - atualMilli;
      if (delta === 0) { target.textContent = 'sem mudanca'; return; }
      const sign = delta > 0 ? '+' : '-';
      target.textContent = sign + formatQty(Math.abs(delta), unit) + ' ' + unit;
    } catch (_) {
      target.textContent = '—';
    }
  }

  function parseSignedQty(text, unit) {
    const s = String(text).trim();
    if (s.charAt(0) === '-') return -parseQty(s.slice(1), unit);
    return parseQty(s, unit);
  }

  async function submitAjuste(ev) {
    ev.preventDefault();
    showError('ajuste-erro', null);
    const productId = parseInt(document.getElementById('ajuste-product-id').value, 10);
    const unit = document.getElementById('ajuste-code').dataset.unit || 'UN';
    const novoText = document.getElementById('ajuste-novo').value;
    const reason = document.getElementById('ajuste-reason').value.trim();

    if (!productId) { showError('ajuste-erro', 'Selecione um produto valido.'); return; }
    if (reason.length < 3) { showError('ajuste-erro', 'Motivo obrigatorio (min 3 caracteres).'); return; }
    let novoMilli;
    try { novoMilli = parseQty(novoText, unit); }
    catch (err) {
      // 0 e valido para ajuste
      if (/vazia|invalida/.test(err.message) && novoText.trim() === '0') {
        novoMilli = 0;
      } else {
        showError('ajuste-erro', err.message); return;
      }
    }

    try {
      await apiFetch(API_AJUSTE, {
        method: 'POST',
        body: JSON.stringify({
          product_id: productId,
          new_stock_milli: novoMilli,
          reason: reason,
        }),
      });
      showFeedback('Ajuste registrado.', 'ok');
      document.getElementById('form-ajuste').reset();
      clearProductBox('ajuste');
      document.getElementById('ajuste-delta').textContent = '—';
    } catch (err) {
      showError('ajuste-erro', err.message);
    }
  }

  // ---------- historico ----------

  function parseDateBR(input) {
    // input type=date retorna ISO yyyy-mm-dd ou vazio
    if (!input) return '';
    return input;
  }

  async function loadHistorico(ev) {
    if (ev) ev.preventDefault();
    const params = new URLSearchParams();
    const productId = document.getElementById('filtro-product-id').value;
    if (productId) params.set('product_id', productId);
    const tipo = document.getElementById('filtro-tipo').value;
    if (tipo) params.set('type', tipo);
    const dateFrom = parseDateBR(document.getElementById('filtro-de').value);
    if (dateFrom) params.set('date_from', new Date(dateFrom + 'T00:00:00').toISOString());
    const dateTo = parseDateBR(document.getElementById('filtro-ate').value);
    if (dateTo) params.set('date_to', new Date(dateTo + 'T23:59:59').toISOString());
    params.set('limit', '200');

    const tbody = document.getElementById('tbody-historico');
    const vazio = document.getElementById('historico-vazio');
    clearNode(tbody);
    vazio.hidden = true;

    try {
      const rows = await apiFetch(API_HISTORICO + '?' + params.toString());
      if (!rows || rows.length === 0) {
        vazio.hidden = false;
        return;
      }
      rows.forEach(r => tbody.appendChild(renderMovementRow(r)));
    } catch (err) {
      showFeedback('Erro ao buscar historico: ' + err.message, 'erro');
    }
  }

  function renderMovementRow(r) {
    const tr = document.createElement('tr');
    tr.appendChild(cell(formatDate(r.created_at)));
    tr.appendChild(cell(r.product_name));
    const tdTipo = document.createElement('td');
    const badge = document.createElement('span');
    badge.className = 'badge badge-' + r.type;
    badge.textContent = TYPE_LABEL[r.type] || r.type;
    tdTipo.appendChild(badge);
    tr.appendChild(tdTipo);
    const tdQty = document.createElement('td');
    tdQty.className = 'num';
    const qtyStr = formatQty(r.qty_milli, r.product_unit);
    tdQty.textContent = (r.qty_milli > 0 ? '+' : '') + qtyStr + ' ' + r.product_unit;
    tr.appendChild(tdQty);
    tr.appendChild(cell(r.reason || ''));
    tr.appendChild(cell(r.user_name || ''));
    return tr;
  }

  function cell(text) {
    const td = document.createElement('td');
    td.textContent = text == null ? '' : String(text);
    return td;
  }

  function formatDate(iso) {
    if (!iso) return '';
    const d = new Date(/Z$|[+-]\d\d:\d\d$/.test(iso) ? iso : iso + 'Z');
    if (isNaN(d.getTime())) return iso;
    const dd = String(d.getDate()).padStart(2, '0');
    const mm = String(d.getMonth() + 1).padStart(2, '0');
    const yyyy = d.getFullYear();
    const hh = String(d.getHours()).padStart(2, '0');
    const mi = String(d.getMinutes()).padStart(2, '0');
    return dd + '/' + mm + '/' + yyyy + ' ' + hh + ':' + mi;
  }

  async function bindFiltroProduto() {
    const field = document.getElementById('filtro-produto');
    field.addEventListener('change', async () => {
      const code = field.value.trim();
      document.getElementById('filtro-product-id').value = '';
      if (!code) return;
      try {
        const product = await resolveProductByCode(code);
        document.getElementById('filtro-product-id').value = String(product.id);
        field.value = product.name;
      } catch (err) {
        showFeedback('Produto nao encontrado.', 'erro');
      }
    });
  }

  function limparFiltros() {
    document.getElementById('form-filtros').reset();
    document.getElementById('filtro-product-id').value = '';
    loadHistorico();
  }

  // ---------- tabs ----------

  function activateTab(name) {
    document.querySelectorAll('.tab').forEach(btn => {
      btn.classList.toggle('active', btn.dataset.tab === name);
    });
    document.querySelectorAll('.tab-panel').forEach(panel => {
      panel.hidden = panel.id !== 'panel-' + name;
    });
    if (name === 'historico') loadHistorico();
  }

  // ---------- logout ----------

  async function doLogout() {
    try {
      await fetch('/auth/logout', {
        method: 'POST',
        headers: { 'X-CSRF-Token': readCookie('csrf_token') },
      });
    } catch (_) { }
    window.location.assign('/login');
  }

  // ---------- init ----------

  document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('.tab').forEach(btn => {
      btn.addEventListener('click', () => activateTab(btn.dataset.tab));
    });

    bindProductLookup('entrada');
    bindProductLookup('perda');
    bindProductLookup('ajuste');
    bindFiltroProduto();

    document.getElementById('form-entrada').addEventListener('submit', submitEntrada);
    document.getElementById('form-perda').addEventListener('submit', submitPerda);
    document.getElementById('form-ajuste').addEventListener('submit', submitAjuste);
    document.getElementById('ajuste-novo').addEventListener('input', updateDeltaPreview);

    document.getElementById('form-filtros').addEventListener('submit', loadHistorico);
    document.getElementById('btn-limpar-filtros').addEventListener('click', limparFiltros);

    document.getElementById('btn-sair').addEventListener('click', doLogout);
  });
})();
