/*
  Relatorios (Fase 8). Admin only.
  Nunca innerHTML com dado do servidor.
*/

(function () {
  'use strict';

  const API_DASH = '/api/reports/dashboard';
  const API_PERIOD = '/api/reports/sales-period';
  const API_CASH = '/api/reports/cash-sessions';
  const API_OPERATOR = '/api/reports/sales-by-operator';
  const API_METHOD = '/api/reports/sales-by-method';
  const API_PRODUCTS = '/api/reports/top-products';
  const API_DISC = '/api/reports/discounts-cancellations';

  function readCookie(name) {
    const pairs = document.cookie ? document.cookie.split(';') : [];
    for (let i = 0; i < pairs.length; i++) {
      const kv = pairs[i].trim().split('=');
      if (kv[0] === name) return decodeURIComponent(kv.slice(1).join('='));
    }
    return '';
  }

  async function apiFetch(path) {
    const resp = await fetch(path, { headers: { 'Accept': 'application/json' } });
    if (resp.status === 401) {
      window.location.assign('/login');
      throw new Error('Nao autenticado.');
    }
    if (!resp.ok) {
      const body = await resp.json().catch(() => ({}));
      throw new Error(body.detail || resp.statusText);
    }
    return await resp.json();
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

  function clearNode(el) { while (el.firstChild) el.removeChild(el.firstChild); }
  function cell(text, cls) {
    const td = document.createElement('td');
    td.textContent = text == null ? '' : String(text);
    if (cls) td.className = cls;
    return td;
  }

  function showFeedback(msg, kind) {
    const el = document.getElementById('feedback');
    clearNode(el);
    el.className = 'feedback';
    if (!msg) return;
    el.classList.add(kind === 'ok' ? 'ok' : 'erro');
    el.textContent = msg;
  }

  // ---------- state ----------

  let filtroDe = '';
  let filtroAte = '';

  function queryString(extra) {
    const p = new URLSearchParams();
    if (filtroDe) p.set('date_from', new Date(filtroDe + 'T00:00:00').toISOString());
    if (filtroAte) p.set('date_to', new Date(filtroAte + 'T23:59:59').toISOString());
    if (extra) Object.keys(extra).forEach(k => { if (extra[k] != null) p.set(k, String(extra[k])); });
    const s = p.toString();
    return s ? '?' + s : '';
  }

  function updateCsvLinks() {
    const qs = queryString();
    document.getElementById('csv-period').href = '/api/reports/sales-period/csv' +
      queryString({ include_cancelled: document.getElementById('chk-incluir-canceladas').checked ? 'true' : 'false' });
    document.getElementById('csv-cash').href = '/api/reports/cash-sessions/csv' + qs;
    document.getElementById('csv-operator').href = '/api/reports/sales-by-operator/csv' + qs;
    document.getElementById('csv-method').href = '/api/reports/sales-by-method/csv' + qs;
    document.getElementById('csv-products').href = '/api/reports/top-products/csv' +
      queryString({
        order_by: document.getElementById('prod-order').value,
        limit: document.getElementById('prod-limit').value,
      });
    document.getElementById('csv-disc').href = '/api/reports/discounts-cancellations/csv' + qs;
  }

  // ---------- loaders ----------

  async function loadDashboard() {
    try {
      const d = await apiFetch(API_DASH);
      document.getElementById('dash-sales-count').textContent = String(d.today_sales_count);
      document.getElementById('dash-revenue').textContent = formatBRL(d.today_revenue_cents);
      document.getElementById('dash-avg').textContent = formatBRL(d.today_avg_ticket_cents);
      document.getElementById('dash-cash').textContent = d.open_cash_session_id
        ? 'Sim (#' + d.open_cash_session_id + ')'
        : 'Nao';
      document.getElementById('dash-low').textContent = String(d.low_stock_count);
    } catch (err) {
      showFeedback('Erro no dashboard: ' + err.message, 'erro');
    }
  }

  async function loadPeriod() {
    const include = document.getElementById('chk-incluir-canceladas').checked;
    const data = await apiFetch(API_PERIOD + queryString({
      include_cancelled: include ? 'true' : 'false',
    }));
    const tbody = document.getElementById('tbody-period');
    const vazio = document.getElementById('period-vazio');
    const tfoot = document.getElementById('tr-period-total');
    clearNode(tbody);
    clearNode(tfoot);
    if (!data.days.length) {
      vazio.hidden = false;
      return;
    }
    vazio.hidden = true;
    data.days.forEach(d => {
      const tr = document.createElement('tr');
      tr.appendChild(cell(d.day));
      tr.appendChild(cell(String(d.sales_count), 'num'));
      tr.appendChild(cell(formatBRL(d.revenue_cents), 'num'));
      tr.appendChild(cell(formatBRL(d.avg_ticket_cents), 'num'));
      tbody.appendChild(tr);
    });
    tfoot.appendChild(cell('TOTAL'));
    tfoot.appendChild(cell(String(data.total_count), 'num'));
    tfoot.appendChild(cell(formatBRL(data.total_revenue_cents), 'num'));
    tfoot.appendChild(cell(formatBRL(data.total_avg_ticket_cents), 'num'));
  }

  async function loadCash() {
    const rows = await apiFetch(API_CASH + queryString());
    const tbody = document.getElementById('tbody-cash');
    const vazio = document.getElementById('cash-vazio');
    clearNode(tbody);
    if (!rows.length) { vazio.hidden = false; return; }
    vazio.hidden = true;
    rows.forEach(r => {
      const tr = document.createElement('tr');
      tr.appendChild(cell(String(r.id)));
      tr.appendChild(cell(formatDate(r.opened_at)));
      tr.appendChild(cell(r.opened_by_name || ''));
      tr.appendChild(cell(formatDate(r.closed_at)));
      tr.appendChild(cell(r.closed_by_name || ''));
      tr.appendChild(cell(formatBRL(r.opening_cash_cents), 'num'));
      tr.appendChild(cell(r.expected_cash_cents != null ? formatBRL(r.expected_cash_cents) : '', 'num'));
      tr.appendChild(cell(r.declared_cash_cents != null ? formatBRL(r.declared_cash_cents) : '', 'num'));
      const tdDiff = cell(r.difference_cents != null ? formatBRL(r.difference_cents) : '', 'num');
      if (r.difference_cents) tdDiff.className += ' ' + (r.difference_cents > 0 ? 'diff-sobra' : 'diff-falta');
      tr.appendChild(tdDiff);
      tr.appendChild(cell(r.difference_reason || ''));
      tbody.appendChild(tr);
    });
  }

  async function loadOperator() {
    const rows = await apiFetch(API_OPERATOR + queryString());
    const tbody = document.getElementById('tbody-operator');
    const vazio = document.getElementById('operator-vazio');
    clearNode(tbody);
    if (!rows.length) { vazio.hidden = false; return; }
    vazio.hidden = true;
    rows.forEach(r => {
      const tr = document.createElement('tr');
      tr.appendChild(cell(r.user_name));
      tr.appendChild(cell(String(r.sales_count), 'num'));
      tr.appendChild(cell(formatBRL(r.revenue_cents), 'num'));
      tr.appendChild(cell(formatBRL(r.discount_total_cents), 'num'));
      tr.appendChild(cell(String(r.cancelled_count), 'num'));
      tbody.appendChild(tr);
    });
  }

  async function loadMethod() {
    const rows = await apiFetch(API_METHOD + queryString());
    const tbody = document.getElementById('tbody-method');
    const vazio = document.getElementById('method-vazio');
    clearNode(tbody);
    if (!rows.length) { vazio.hidden = false; return; }
    vazio.hidden = true;
    rows.forEach(r => {
      const tr = document.createElement('tr');
      tr.appendChild(cell(r.method));
      tr.appendChild(cell(String(r.sales_count), 'num'));
      tr.appendChild(cell(formatBRL(r.total_cents), 'num'));
      tbody.appendChild(tr);
    });
  }

  async function loadProducts() {
    const order_by = document.getElementById('prod-order').value;
    const limit = document.getElementById('prod-limit').value || '20';
    const rows = await apiFetch(API_PRODUCTS + queryString({ order_by, limit }));
    const tbody = document.getElementById('tbody-products');
    const vazio = document.getElementById('products-vazio');
    clearNode(tbody);
    if (!rows.length) { vazio.hidden = false; return; }
    vazio.hidden = true;
    rows.forEach((r, i) => {
      const tr = document.createElement('tr');
      tr.appendChild(cell(String(i + 1)));
      tr.appendChild(cell(r.product_name));
      tr.appendChild(cell(r.unit));
      tr.appendChild(cell(formatQty(r.qty_milli, r.unit), 'num'));
      tr.appendChild(cell(formatBRL(r.revenue_cents), 'num'));
      tbody.appendChild(tr);
    });
  }

  async function loadDisc() {
    const rows = await apiFetch(API_DISC + queryString());
    const tbody = document.getElementById('tbody-disc');
    const vazio = document.getElementById('disc-vazio');
    clearNode(tbody);
    if (!rows.length) { vazio.hidden = false; return; }
    vazio.hidden = true;
    rows.forEach(r => {
      const tr = document.createElement('tr');
      tr.appendChild(cell('#' + r.sale_number));
      const tdKind = document.createElement('td');
      const badge = document.createElement('span');
      badge.className = 'badge badge-' + (r.kind === 'cancelamento' ? 'perda' : 'ajuste');
      badge.textContent = r.kind;
      tdKind.appendChild(badge);
      tr.appendChild(tdKind);
      tr.appendChild(cell(formatDate(r.occurred_at)));
      tr.appendChild(cell(r.user_name || ''));
      tr.appendChild(cell(formatBRL(r.total_cents), 'num'));
      tr.appendChild(cell(formatBRL(r.discount_cents), 'num'));
      tr.appendChild(cell(r.reason || ''));
      tbody.appendChild(tr);
    });
  }

  const LOADERS = {
    period: loadPeriod,
    cash: loadCash,
    operator: loadOperator,
    method: loadMethod,
    products: loadProducts,
    disc: loadDisc,
  };

  let activeTab = 'period';

  async function reloadActive() {
    updateCsvLinks();
    const loader = LOADERS[activeTab];
    if (!loader) return;
    try { await loader(); }
    catch (err) { showFeedback('Erro: ' + err.message, 'erro'); }
  }

  function activateTab(name) {
    activeTab = name;
    document.querySelectorAll('.tab').forEach(btn => {
      btn.classList.toggle('active', btn.dataset.tab === name);
    });
    document.querySelectorAll('.tab-panel').forEach(panel => {
      panel.hidden = panel.id !== 'panel-' + name;
    });
    reloadActive();
  }

  function aplicarFiltros(ev) {
    if (ev) ev.preventDefault();
    filtroDe = document.getElementById('filtro-de').value;
    filtroAte = document.getElementById('filtro-ate').value;
    reloadActive();
  }

  function limparFiltros() {
    document.getElementById('filtro-de').value = '';
    document.getElementById('filtro-ate').value = '';
    filtroDe = '';
    filtroAte = '';
    reloadActive();
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

  document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('.tab').forEach(btn => {
      btn.addEventListener('click', () => activateTab(btn.dataset.tab));
    });
    document.getElementById('form-filtros').addEventListener('submit', aplicarFiltros);
    document.getElementById('btn-limpar').addEventListener('click', limparFiltros);
    document.getElementById('chk-incluir-canceladas').addEventListener('change', reloadActive);
    document.getElementById('prod-order').addEventListener('change', reloadActive);
    document.getElementById('prod-limit').addEventListener('change', reloadActive);
    document.getElementById('btn-sair').addEventListener('click', doLogout);

    loadDashboard();
    reloadActive();
  });
})();
