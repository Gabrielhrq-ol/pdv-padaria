/* Painel admin (Fase 11). */

(function () {
  'use strict';

  const API_DASH = '/api/reports/dashboard';
  const API_MARGINS = '/api/reports/margins';
  const API_LOW = '/api/admin/stock/low';
  const API_BACKUP_HIST = '/api/admin/backup/history?limit=5';

  function readCookie(name) {
    const pairs = document.cookie ? document.cookie.split(';') : [];
    for (let i = 0; i < pairs.length; i++) {
      const kv = pairs[i].trim().split('=');
      if (kv[0] === name) return decodeURIComponent(kv.slice(1).join('='));
    }
    return '';
  }

  async function fetchJson(path) {
    const resp = await fetch(path, { headers: { 'Accept': 'application/json' } });
    if (resp.status === 401) { window.location.assign('/login'); throw new Error('nao auth'); }
    if (!resp.ok) throw new Error((await resp.json().catch(() => ({}))).detail || resp.statusText);
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

  function clearNode(el) { while (el.firstChild) el.removeChild(el.firstChild); }

  function cell(text, cls) {
    const td = document.createElement('td');
    td.textContent = text == null ? '' : String(text);
    if (cls) td.className = cls;
    return td;
  }

  async function loadDashboard() {
    try {
      const d = await fetchJson(API_DASH);
      document.getElementById('dash-sales-count').textContent = String(d.today_sales_count);
      document.getElementById('dash-revenue').textContent = formatBRL(d.today_revenue_cents);
      document.getElementById('dash-avg').textContent = formatBRL(d.today_avg_ticket_cents);
      document.getElementById('dash-margin').textContent = formatBRL(d.today_margin_cents);
      const pctEl = document.getElementById('dash-margin-pct');
      if (d.today_margin_covered_items > 0) {
        pctEl.textContent = d.today_margin_pct.toFixed(2).replace('.', ',') + '%';
      } else {
        pctEl.textContent = '';
      }
      const coverEl = document.getElementById('dash-margin-cover');
      if (d.today_margin_total_items > 0 &&
          d.today_margin_covered_items < d.today_margin_total_items) {
        coverEl.textContent = 'calculada em ' + d.today_margin_covered_items +
          ' de ' + d.today_margin_total_items + ' itens (sem custo cadastrado)';
      } else {
        coverEl.textContent = '';
      }
    } catch (err) {
      // nao mostrar erro, deixa valor vazio
    }
  }

  async function loadAlerts() {
    const list = document.getElementById('alerts-list');
    const card = document.getElementById('alerts-card');
    clearNode(list);

    const items = [];

    try {
      const low = await fetchJson(API_LOW);
      if (low && low.length) {
        items.push({
          text: low.length + ' produto(s) com estoque abaixo do minimo',
          href: '/admin/stock',
          cls: 'badge-perda',
        });
      }
    } catch (_) {}

    try {
      const hist = await fetchJson(API_BACKUP_HIST);
      const recent = (hist || []).slice(0, 3);
      const failed = recent.find(h => h.action === 'backup_failed' || h.action === 'backup_skipped');
      if (failed) {
        items.push({
          text: 'Backup recente teve problema (' + failed.action + ')',
          href: '/admin/backup',
          cls: 'badge-perda',
        });
      } else if (recent.length === 0) {
        items.push({
          text: 'Nenhum backup executado ainda',
          href: '/admin/backup',
          cls: 'badge-ajuste',
        });
      }
    } catch (_) {}

    if (!items.length) {
      card.hidden = true;
      return;
    }
    card.hidden = false;
    items.forEach(it => {
      const li = document.createElement('li');
      const badge = document.createElement('span');
      badge.className = 'badge ' + it.cls;
      badge.textContent = 'ALERTA';
      li.appendChild(badge);
      const link = document.createElement('a');
      link.href = it.href;
      link.textContent = it.text;
      li.appendChild(link);
      list.appendChild(li);
    });
  }

  async function loadMargins() {
    const tbody = document.getElementById('tbody-margins');
    const vazio = document.getElementById('margins-vazio');
    const uncovered = document.getElementById('margins-uncovered');
    clearNode(tbody);

    const today = new Date();
    const y = today.getFullYear();
    const m = String(today.getMonth() + 1).padStart(2, '0');
    const d = String(today.getDate()).padStart(2, '0');
    const dateFrom = `${y}-${m}-${d}T00:00:00`;
    const dateTo = `${y}-${m}-${d}T23:59:59`;

    try {
      const r = await fetchJson(
        API_MARGINS + '?date_from=' + encodeURIComponent(dateFrom) +
        '&date_to=' + encodeURIComponent(dateTo) +
        '&order_by=margin&limit=10'
      );
      if (!r.rows.length) {
        vazio.hidden = false;
      } else {
        vazio.hidden = true;
        r.rows.forEach(row => {
          const tr = document.createElement('tr');
          tr.appendChild(cell(row.product_name));
          tr.appendChild(cell(formatQty(row.qty_milli, row.unit) + ' ' + row.unit, 'num'));
          tr.appendChild(cell(formatBRL(row.revenue_cents), 'num'));
          const tdMargin = cell(formatBRL(row.margin_cents), 'num');
          tdMargin.classList.add(row.margin_cents >= 0 ? 'diff-sobra' : 'diff-falta');
          tr.appendChild(tdMargin);
          tr.appendChild(cell(row.margin_pct.toFixed(2).replace('.', ',') + '%', 'num'));
          tbody.appendChild(tr);
        });
      }
      if (r.uncovered_items > 0) {
        uncovered.hidden = false;
        uncovered.textContent = r.uncovered_items +
          ' linha(s) de venda sem custo cadastrado foram ignoradas no calculo.';
      } else {
        uncovered.hidden = true;
      }
    } catch (_) {
      vazio.hidden = false;
    }
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
    document.getElementById('btn-sair').addEventListener('click', doLogout);
    loadDashboard();
    loadAlerts();
    loadMargins();
  });
})();
