/*
  Admin -> Backup (Fase 9).
  Nunca innerHTML com dado do servidor.
*/

(function () {
  'use strict';

  const API_SETTINGS = '/api/admin/backup/settings';
  const API_RUN = '/api/admin/backup/run';
  const API_HISTORY = '/api/admin/backup/history';

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
    if (resp.status === 401) { window.location.assign('/login'); throw new Error('Nao autenticado.'); }
    const body = await resp.json().catch(() => ({}));
    if (!resp.ok) {
      let msg = body.detail || resp.statusText || 'Erro.';
      if (Array.isArray(body.errors)) msg += ' ' + body.errors.map(e => e.msg).join('; ');
      throw new Error(msg);
    }
    return body;
  }

  function clearNode(el) { while (el.firstChild) el.removeChild(el.firstChild); }
  function cell(text) {
    const td = document.createElement('td');
    td.textContent = text == null ? '' : String(text);
    return td;
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
      if (el.textContent === msg) { clearNode(el); el.className = 'feedback'; }
    }, 4000);
  }

  function formatDate(iso) {
    if (!iso) return '';
    const d = new Date(iso);
    if (isNaN(d.getTime())) return iso;
    const dd = String(d.getDate()).padStart(2, '0');
    const mm = String(d.getMonth() + 1).padStart(2, '0');
    const yyyy = d.getFullYear();
    const hh = String(d.getHours()).padStart(2, '0');
    const mi = String(d.getMinutes()).padStart(2, '0');
    const ss = String(d.getSeconds()).padStart(2, '0');
    return dd + '/' + mm + '/' + yyyy + ' ' + hh + ':' + mi + ':' + ss;
  }

  function formatBytes(n) {
    if (n < 1024) return n + ' B';
    if (n < 1024 * 1024) return (n / 1024).toFixed(1) + ' KB';
    return (n / (1024 * 1024)).toFixed(2) + ' MB';
  }

  // ---------- settings ----------

  async function loadSettings() {
    const s = await apiFetch(API_SETTINGS);
    document.getElementById('dir1').value = s.backup_dir_1 || '';
    document.getElementById('dir2').value = s.backup_dir_2 || '';
    document.getElementById('keep').value = s.backup_keep;
    document.getElementById('on-close').checked = !!s.backup_on_cash_close;
    document.getElementById('compress').checked = !!s.backup_compress;
    // Fase 17 (B5): warnings do backend sobre paths nao-externos
    if (s.warnings && s.warnings.length) {
      s.warnings.forEach(w => showFeedback('AVISO: ' + w, 'erro'));
    }
  }

  async function saveSettings(ev) {
    ev.preventDefault();
    showError('settings-erro', null);
    const payload = {
      backup_dir_1: document.getElementById('dir1').value.trim() || null,
      backup_dir_2: document.getElementById('dir2').value.trim() || null,
      backup_keep: parseInt(document.getElementById('keep').value, 10) || 30,
      backup_on_cash_close: document.getElementById('on-close').checked,
      backup_compress: document.getElementById('compress').checked,
    };
    try {
      await apiFetch(API_SETTINGS, { method: 'PUT', body: JSON.stringify(payload) });
      showFeedback('Configuracao salva.', 'ok');
    } catch (err) {
      showError('settings-erro', err.message);
    }
  }

  // ---------- run ----------

  async function runNow() {
    const box = document.getElementById('run-result');
    box.hidden = false;
    clearNode(box);
    const p = document.createElement('p');
    p.textContent = 'Rodando backup...';
    box.appendChild(p);
    try {
      const r = await apiFetch(API_RUN, { method: 'POST' });
      clearNode(box);
      const status = document.createElement('p');
      status.className = r.fail_count === 0 ? 'result-ok' : 'result-erro';
      status.textContent = r.ok_count + '/' + (r.ok_count + r.fail_count) + ' destinos OK ' +
        '(fonte ' + formatBytes(r.source_bytes) + ', gzip=' + r.compressed + ')';
      box.appendChild(status);
      r.results.forEach(d => {
        const line = document.createElement('p');
        line.className = d.status === 'ok' ? 'result-ok' : 'result-erro';
        if (d.status === 'ok') {
          line.textContent = 'OK  ' + d.destination + '  ' + d.file_name + '  (' + formatBytes(d.bytes_written) + ')';
        } else {
          line.textContent = 'FALHA  ' + d.destination + '  ' + d.error;
        }
        box.appendChild(line);
      });
      await loadHistory();
    } catch (err) {
      clearNode(box);
      const e = document.createElement('p');
      e.className = 'result-erro';
      e.textContent = 'Erro: ' + err.message;
      box.appendChild(e);
    }
  }

  // ---------- history ----------

  async function loadHistory() {
    try {
      const rows = await apiFetch(API_HISTORY + '?limit=50');
      const tbody = document.getElementById('tbody-history');
      const vazio = document.getElementById('history-vazio');
      clearNode(tbody);
      if (!rows.length) { vazio.hidden = false; return; }
      vazio.hidden = true;
      rows.forEach(r => {
        const tr = document.createElement('tr');
        tr.appendChild(cell(formatDate(r.created_at)));
        tr.appendChild(cell(r.user_name || '(sistema)'));
        const tdAct = document.createElement('td');
        const badge = document.createElement('span');
        let cls = 'badge-entrada';
        if (r.action === 'backup_failed') cls = 'badge-perda';
        else if (r.action === 'backup_skipped') cls = 'badge-estorno';
        badge.className = 'badge ' + cls;
        badge.textContent = r.action;
        tdAct.appendChild(badge);
        tr.appendChild(tdAct);
        tr.appendChild(cell(r.details || ''));
        tbody.appendChild(tr);
      });
    } catch (err) {
      showFeedback('Erro no historico: ' + err.message, 'erro');
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
    document.getElementById('form-settings').addEventListener('submit', saveSettings);
    document.getElementById('btn-run').addEventListener('click', runNow);
    document.getElementById('btn-sair').addEventListener('click', doLogout);
    loadSettings();
    loadHistory();
  });
})();
