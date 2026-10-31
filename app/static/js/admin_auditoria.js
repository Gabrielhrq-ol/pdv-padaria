/* Auditoria (Fase 16). Admin only. */

(function () {
  'use strict';

  const API_AUDIT = '/api/admin/audit-log';
  const API_ACTIONS = '/api/admin/audit-log/actions';
  const API_USERS = '/api/admin/users';
  const PAGE_SIZE = 100;

  let offset = 0;
  let currentRows = [];

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
    td.textContent = text == null ? '-' : String(text);
    if (cls) td.className = cls;
    return td;
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
    const ss = String(d.getSeconds()).padStart(2, '0');
    return dd + '/' + mm + '/' + yyyy + ' ' + hh + ':' + mi + ':' + ss;
  }

  function showFeedback(msg, kind) {
    const el = document.getElementById('feedback');
    clearNode(el); el.className = 'feedback';
    if (!msg) return;
    el.classList.add(kind === 'ok' ? 'ok' : 'erro');
    el.textContent = msg;
    setTimeout(() => {
      if (el.textContent === msg) { clearNode(el); el.className = 'feedback'; }
    }, 4000);
  }

  // Classifica acao em cor por grupo
  function actionBadgeClass(action) {
    if (action.startsWith('login_fail') || action.endsWith('_failed')
        || action === 'lockout' || action.startsWith('sale_reversed')
        || action.endsWith('_deactivated') || action === 'cash_closed') {
      return 'badge-perda';
    }
    if (action.startsWith('login_ok') || action.endsWith('_created')
        || action.endsWith('_activated') || action === 'cash_opened'
        || action === 'backup_run' || action === 'stock_entry') {
      return 'badge-entrada';
    }
    if (action === 'backup_skipped' || action.endsWith('_updated')
        || action.endsWith('_changed') || action === 'stock_adjustment') {
      return 'badge-ajuste';
    }
    if (action === 'cash_sangria') return 'badge-perda';
    if (action === 'cash_suprimento') return 'badge-entrada';
    return 'badge-estorno';
  }

  // ---------- loaders ----------

  async function loadActions() {
    try {
      const actions = await apiFetch(API_ACTIONS);
      const sel = document.getElementById('filtro-action');
      actions.forEach(a => {
        const opt = document.createElement('option');
        opt.value = a; opt.textContent = a;
        sel.appendChild(opt);
      });
    } catch (_) {}
  }

  async function loadUsers() {
    try {
      const list = await apiFetch(API_USERS);
      const sel = document.getElementById('filtro-user');
      list.forEach(u => {
        const opt = document.createElement('option');
        opt.value = String(u.id);
        opt.textContent = u.name + ' (' + u.username + ')';
        sel.appendChild(opt);
      });
    } catch (_) {}
  }

  function buildQuery() {
    const p = new URLSearchParams();
    const a = document.getElementById('filtro-action').value;
    const u = document.getElementById('filtro-user').value;
    const e = document.getElementById('filtro-entity').value;
    const de = document.getElementById('filtro-de').value;
    const ate = document.getElementById('filtro-ate').value;
    if (a) p.set('action', a);
    if (u) p.set('user_id', u);
    if (e) p.set('entity', e);
    if (de) p.set('date_from', new Date(de + 'T00:00:00').toISOString());
    if (ate) p.set('date_to', new Date(ate + 'T23:59:59').toISOString());
    p.set('limit', String(PAGE_SIZE));
    p.set('offset', String(offset));
    return p.toString();
  }

  async function loadAudit() {
    const tbody = document.getElementById('tbody-audit');
    const vazio = document.getElementById('audit-vazio');
    clearNode(tbody);
    try {
      currentRows = await apiFetch(API_AUDIT + '?' + buildQuery());
    } catch (err) {
      showFeedback('Erro: ' + err.message, 'erro');
      return;
    }
    document.getElementById('pager-info').textContent =
      currentRows.length === 0
        ? 'Nenhum evento'
        : `${offset + 1}–${offset + currentRows.length}`;
    document.getElementById('btn-prev').disabled = offset === 0;
    document.getElementById('btn-next').disabled = currentRows.length < PAGE_SIZE;

    if (!currentRows.length) { vazio.hidden = false; return; }
    vazio.hidden = true;
    currentRows.forEach(r => {
      const tr = document.createElement('tr');
      tr.appendChild(cell(formatDate(r.created_at)));
      tr.appendChild(cell(r.user_name || '(sistema)'));
      const tdA = document.createElement('td');
      const b = document.createElement('span');
      b.className = 'badge ' + actionBadgeClass(r.action);
      b.textContent = r.action;
      tdA.appendChild(b);
      tr.appendChild(tdA);
      tr.appendChild(cell(r.entity));
      tr.appendChild(cell(r.entity_id != null ? String(r.entity_id) : '-'));
      tr.appendChild(cell(r.details));
      tr.appendChild(cell(r.ip));
      tbody.appendChild(tr);
    });
  }

  function aplicar(ev) {
    if (ev) ev.preventDefault();
    offset = 0;
    loadAudit();
  }

  function limpar() {
    document.getElementById('form-filtros').reset();
    offset = 0;
    loadAudit();
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
      offset = Math.max(0, offset - PAGE_SIZE); loadAudit();
    });
    document.getElementById('btn-next').addEventListener('click', () => {
      offset += PAGE_SIZE; loadAudit();
    });
    document.getElementById('btn-sair').addEventListener('click', doLogout);

    await Promise.all([loadActions(), loadUsers()]);
    await loadAudit();
  });
})();
