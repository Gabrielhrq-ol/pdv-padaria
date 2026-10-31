/* Historico de vendas (Fase 15). Admin only. */

(function () {
  'use strict';

  const API_SALES = '/api/sales';
  const API_USERS = '/api/admin/users';
  const PAGE_SIZE = 50;

  let offset = 0;
  let currentRows = [];
  let usersById = {};

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
    if (resp.status === 401) { window.location.assign('/login'); throw new Error('nao auth'); }
    const body = await resp.json().catch(() => ({}));
    if (!resp.ok) {
      let msg = body.detail || resp.statusText || 'Erro.';
      if (Array.isArray(body.errors)) msg += ' ' + body.errors.map(e => e.msg).join('; ');
      throw new Error(msg);
    }
    return body;
  }

  function clearNode(el) { while (el.firstChild) el.removeChild(el.firstChild); }
  function cell(text, cls) {
    const td = document.createElement('td');
    td.textContent = text == null ? '' : String(text);
    if (cls) td.className = cls;
    return td;
  }
  function el(tag, attrs, children) {
    const n = document.createElement(tag);
    if (attrs) {
      for (const k in attrs) {
        if (k === 'className') n.className = attrs[k];
        else if (k === 'onclick') n.addEventListener('click', attrs[k]);
        else n.setAttribute(k, attrs[k]);
      }
    }
    (children || []).forEach(c => {
      if (c == null) return;
      if (typeof c === 'string') n.appendChild(document.createTextNode(c));
      else n.appendChild(c);
    });
    return n;
  }

  function formatBRL(cents) {
    const neg = cents < 0;
    const abs = Math.abs(cents | 0);
    const reais = Math.floor(abs / 100);
    const cs = (abs % 100).toString().padStart(2, '0');
    return (neg ? 'R$ -' : 'R$ ') + reais.toLocaleString('pt-BR') + ',' + cs;
  }
  function formatQty(milli, unit) {
    const abs = Math.abs(milli | 0);
    const inteiro = Math.floor(abs / 1000);
    const resto = (abs % 1000).toString().padStart(3, '0');
    if (unit === 'UN' && abs % 1000 === 0) return String(abs / 1000);
    return inteiro + ',' + resto;
  }
  function formatDate(iso) {
    if (!iso) return '-';
    const d = new Date(/Z$|[+-]\d\d:\d\d$/.test(iso) ? iso : iso + 'Z');
    if (isNaN(d.getTime())) return iso;
    const dd = String(d.getDate()).padStart(2, '0');
    const mm = String(d.getMonth() + 1).padStart(2, '0');
    const yyyy = d.getFullYear();
    const hh = String(d.getHours()).padStart(2, '0');
    const mi = String(d.getMinutes()).padStart(2, '0');
    return dd + '/' + mm + '/' + yyyy + ' ' + hh + ':' + mi;
  }

  function showError(id, msg) {
    const e = document.getElementById(id);
    if (!e) return;
    if (!msg) { e.hidden = true; e.textContent = ''; return; }
    e.hidden = false; e.textContent = msg;
  }

  function showFeedback(msg, kind) {
    const e = document.getElementById('feedback');
    clearNode(e); e.className = 'feedback';
    if (!msg) return;
    e.classList.add(kind === 'ok' ? 'ok' : 'erro');
    e.textContent = msg;
    setTimeout(() => {
      if (e.textContent === msg) { clearNode(e); e.className = 'feedback'; }
    }, 4000);
  }

  // ---------- carregamento ----------

  async function loadUsers() {
    try {
      const list = await apiFetch(API_USERS);
      usersById = {};
      const sel = document.getElementById('filtro-user');
      list.forEach(u => {
        usersById[u.id] = u;
        const opt = document.createElement('option');
        opt.value = String(u.id);
        opt.textContent = u.name + ' (' + u.username + ')';
        sel.appendChild(opt);
      });
    } catch (err) {
      // nao bloqueia a tela se nao carregou users
    }
  }

  function buildQuery() {
    const p = new URLSearchParams();
    const num = document.getElementById('filtro-numero').value.trim();
    if (num) p.set('number', num);
    else {
      const de = document.getElementById('filtro-de').value;
      const ate = document.getElementById('filtro-ate').value;
      const st = document.getElementById('filtro-status').value;
      const uid = document.getElementById('filtro-user').value;
      if (de) p.set('date_from', new Date(de + 'T00:00:00').toISOString());
      if (ate) p.set('date_to', new Date(ate + 'T23:59:59').toISOString());
      if (st) p.set('status', st);
      if (uid) p.set('user_id', uid);
    }
    p.set('limit', String(PAGE_SIZE));
    p.set('offset', String(offset));
    return p.toString();
  }

  async function loadVendas() {
    const tbody = document.getElementById('tbody-vendas');
    const vazio = document.getElementById('vendas-vazio');
    clearNode(tbody);
    try {
      currentRows = await apiFetch(API_SALES + '?' + buildQuery());
    } catch (err) {
      showFeedback('Erro: ' + err.message, 'erro');
      return;
    }
    document.getElementById('pager-info').textContent =
      currentRows.length === 0
        ? 'Nenhuma venda'
        : `${offset + 1}–${offset + currentRows.length}`;
    document.getElementById('btn-prev').disabled = offset === 0;
    document.getElementById('btn-next').disabled = currentRows.length < PAGE_SIZE;
    if (!currentRows.length) { vazio.hidden = false; return; }
    vazio.hidden = true;
    currentRows.forEach(s => {
      const tr = document.createElement('tr');
      if (s.status === 'cancelled') tr.classList.add('inativo');
      tr.appendChild(cell(String(s.number).padStart(6, '0')));
      tr.appendChild(cell(formatDate(s.finalized_at || s.created_at)));
      tr.appendChild(cell((usersById[s.user_id] || {}).name || '#' + s.user_id));
      const tdSt = document.createElement('td');
      const b = document.createElement('span');
      b.className = 'badge ' + statusBadge(s.status);
      b.textContent = statusLabel(s.status);
      tdSt.appendChild(b);
      tr.appendChild(tdSt);
      tr.appendChild(cell(String((s.items || []).length), 'num'));
      tr.appendChild(cell(formatBRL(s.total_cents), 'num'));

      const tdAct = document.createElement('td');
      tdAct.className = 'actions';
      const btnView = document.createElement('button');
      btnView.type = 'button';
      btnView.className = 'btn btn-sm';
      btnView.textContent = 'Ver';
      btnView.addEventListener('click', () => openDetail(s));
      tdAct.appendChild(btnView);
      tr.appendChild(tdAct);
      tbody.appendChild(tr);
    });
  }

  function statusBadge(st) {
    if (st === 'completed') return 'badge-entrada';
    if (st === 'cancelled') return 'badge-perda';
    return 'badge-ajuste';
  }
  function statusLabel(st) {
    if (st === 'completed') return 'finalizada';
    if (st === 'cancelled') return 'cancelada';
    return 'em aberto';
  }

  // ---------- detalhe ----------

  async function openDetail(s) {
    // Busca completa pra pegar items + payments
    let full;
    try {
      full = await apiFetch(API_SALES + '/' + s.id);
    } catch (err) {
      showFeedback('Erro: ' + err.message, 'erro');
      return;
    }
    document.getElementById('sale-num').textContent = '#' + String(full.number).padStart(6, '0');
    const body = document.getElementById('sale-detail-body');
    clearNode(body);

    // Status + resumo
    const resumo = el('div', { className: 'ops-status' }, [
      el('div', null, [
        el('div', { className: 'ops-stat-label' }, ['Status']),
        el('div', { className: 'ops-stat-value' }, [statusLabel(full.status)]),
      ]),
      el('div', null, [
        el('div', { className: 'ops-stat-label' }, ['Operador']),
        el('div', { className: 'ops-stat-value' }, [(usersById[full.user_id] || {}).name || '#' + full.user_id]),
      ]),
      el('div', null, [
        el('div', { className: 'ops-stat-label' }, ['Finalizada em']),
        el('div', { className: 'ops-stat-value' }, [formatDate(full.finalized_at)]),
      ]),
      el('div', null, [
        el('div', { className: 'ops-stat-label' }, ['Total']),
        el('div', { className: 'ops-stat-value' }, [formatBRL(full.total_cents)]),
      ]),
    ]);
    body.appendChild(resumo);

    // Itens
    body.appendChild(el('h3', null, ['Itens']));
    const tItens = el('table', { className: 'table-produtos' });
    const thead = el('thead', null, [el('tr', null, [
      el('th', null, ['#']),
      el('th', null, ['Produto']),
      el('th', { className: 'num' }, ['Qtd']),
      el('th', { className: 'num' }, ['Unit.']),
      el('th', { className: 'num' }, ['Total']),
    ])]);
    tItens.appendChild(thead);
    const tbodyIt = el('tbody');
    (full.items || []).forEach((it, idx) => {
      const tr = el('tr', null, [
        cell(String(idx + 1)),
        cell(it.product_name),
        cell(formatQty(it.qty_milli, it.unit) + ' ' + it.unit, 'num'),
        cell(formatBRL(it.unit_price_cents), 'num'),
        cell(formatBRL(it.line_total_cents), 'num'),
      ]);
      tbodyIt.appendChild(tr);
    });
    tItens.appendChild(tbodyIt);
    body.appendChild(tItens);

    // Pagamentos
    body.appendChild(el('h3', null, ['Pagamentos']));
    const tPays = el('table', { className: 'table-produtos' });
    const theadP = el('thead', null, [el('tr', null, [
      el('th', null, ['Forma']),
      el('th', { className: 'num' }, ['Valor']),
      el('th', { className: 'num' }, ['Troco']),
    ])]);
    tPays.appendChild(theadP);
    const tbodyP = el('tbody');
    (full.payments || []).forEach(p => {
      tbodyP.appendChild(el('tr', null, [
        cell(p.method),
        cell(formatBRL(p.amount_cents), 'num'),
        cell(p.change_cents > 0 ? formatBRL(p.change_cents) : '-', 'num'),
      ]));
    });
    tPays.appendChild(tbodyP);
    body.appendChild(tPays);

    // Cancelamento (se tem)
    if (full.status === 'cancelled' && full.cancel_reason) {
      body.appendChild(el('div', { className: 'erro-form', style: 'display:block;margin-top:10px;' }, [
        'Cancelada: ' + full.cancel_reason,
      ]));
    }

    // Acoes
    const actions = el('div', { className: 'modal-actions', style: 'margin-top:16px;' });
    if (full.status === 'completed') {
      const btnReprint = el('button', {
        type: 'button', className: 'btn',
        onclick: () => reprintSale(full),
      }, ['Reimprimir']);
      actions.appendChild(btnReprint);
      const btnReverse = el('button', {
        type: 'button', className: 'btn btn-danger',
        onclick: () => openReverse(full),
      }, ['Estornar']);
      actions.appendChild(btnReverse);
    }
    actions.appendChild(el('button', {
      type: 'button', className: 'btn',
      onclick: () => closeModal('modal-sale'),
    }, ['Fechar']));
    body.appendChild(actions);

    document.getElementById('modal-sale').hidden = false;
  }

  async function reprintSale(s) {
    try {
      const r = await apiFetch(API_SALES + '/' + s.id + '/reprint', { method: 'POST' });
      if (r.printed) showFeedback('Reimpresso (' + s.id + ').', 'ok');
      else showFeedback('Enviado ao Dummy — veja o log do servidor.', 'ok');
    } catch (err) {
      showFeedback('Erro reimprimir: ' + err.message, 'erro');
    }
  }

  // ---------- estorno ----------

  function openReverse(s) {
    document.getElementById('reverse-sale-id').value = String(s.id);
    document.getElementById('reverse-reason').value = '';
    showError('reverse-erro', null);
    document.getElementById('modal-reverse').hidden = false;
    setTimeout(() => document.getElementById('reverse-reason').focus(), 10);
  }

  async function submitReverse(ev) {
    ev.preventDefault();
    showError('reverse-erro', null);
    const id = document.getElementById('reverse-sale-id').value;
    const reason = document.getElementById('reverse-reason').value.trim();
    if (reason.length < 3) {
      showError('reverse-erro', 'Motivo min 3 caracteres.');
      return;
    }
    try {
      await apiFetch(API_SALES + '/' + id + '/reverse', {
        method: 'POST',
        body: JSON.stringify({ reason }),
      });
      showFeedback('Venda estornada.', 'ok');
      closeModal('modal-reverse');
      closeModal('modal-sale');
      await loadVendas();
    } catch (err) {
      showError('reverse-erro', err.message);
    }
  }

  // ---------- modal control ----------

  function closeModal(id) {
    const m = document.getElementById(id);
    if (m) m.hidden = true;
  }

  function aplicar(ev) {
    if (ev) ev.preventDefault();
    offset = 0;
    loadVendas();
  }

  function limpar() {
    document.getElementById('form-filtros').reset();
    offset = 0;
    loadVendas();
  }

  async function doLogout() {
    try {
      await fetch('/auth/logout', {
        method: 'POST',
        headers: { 'X-CSRF-Token': readCookie('csrf_token') },
      });
    } catch (_) {}
    window.location.assign('/login');
  }

  document.addEventListener('DOMContentLoaded', async () => {
    document.getElementById('form-filtros').addEventListener('submit', aplicar);
    document.getElementById('btn-limpar').addEventListener('click', limpar);
    document.getElementById('btn-prev').addEventListener('click', () => {
      offset = Math.max(0, offset - PAGE_SIZE); loadVendas();
    });
    document.getElementById('btn-next').addEventListener('click', () => {
      offset += PAGE_SIZE; loadVendas();
    });
    document.getElementById('form-reverse').addEventListener('submit', submitReverse);
    document.getElementById('btn-sair').addEventListener('click', doLogout);

    document.querySelectorAll('[data-close]').forEach(b => {
      b.addEventListener('click', () => closeModal(b.dataset.close));
    });
    ['modal-sale', 'modal-reverse'].forEach(id => {
      const m = document.getElementById(id);
      m.addEventListener('click', (ev) => { if (ev.target === m) closeModal(id); });
    });

    await loadUsers();
    await loadVendas();
  });
})();
