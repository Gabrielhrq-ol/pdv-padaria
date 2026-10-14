/*
  Admin -> Configuracao da impressora.
  REGRA: nunca innerHTML com dado do servidor.
*/

(function () {
  'use strict';

  const API = '/api/admin/printer-settings';
  const API_TEST = '/api/admin/printer-test';

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
        msg = msg + '\n' + body.errors.map(e => e.msg).join('\n');
      }
      throw new Error(msg);
    }
    return body;
  }

  function clearNode(el) {
    while (el.firstChild) el.removeChild(el.firstChild);
  }

  function showError(msg) {
    const el = document.getElementById('erro-form');
    if (!msg) { el.hidden = true; el.textContent = ''; return; }
    el.hidden = false;
    el.textContent = msg;
  }

  function updateVisibility() {
    const backend = document.getElementById('field-backend').value;
    const needsName = backend === 'win32raw';
    document.getElementById('row-name').style.display = needsName ? '' : 'none';
    document.getElementById('row-codepage').style.display = needsName ? '' : 'none';
  }

  function fillForm(data) {
    document.getElementById('field-backend').value = data.printer_backend;
    document.getElementById('field-name').value = data.printer_name || '';
    document.getElementById('field-codepage').value = data.printer_codepage || '';
    document.getElementById('field-cut').checked = !!data.printer_auto_cut;
    document.getElementById('label-ativo').textContent = data.active_label || '';
    updateVisibility();
  }

  async function loadSettings() {
    try {
      const data = await apiFetch(API);
      fillForm(data);
    } catch (err) {
      showError('Erro ao carregar: ' + err.message);
    }
  }

  async function saveSettings(ev) {
    ev.preventDefault();
    showError(null);
    const payload = {
      printer_backend: document.getElementById('field-backend').value,
      printer_name: document.getElementById('field-name').value.trim(),
      printer_codepage: document.getElementById('field-codepage').value,
      printer_auto_cut: document.getElementById('field-cut').checked,
    };
    try {
      const data = await apiFetch(API, {
        method: 'PUT',
        body: JSON.stringify(payload),
      });
      fillForm(data);
      showResult('Configurações salvas.', 'ok');
    } catch (err) {
      showError(err.message);
    }
  }

  function showResult(msg, type) {
    const box = document.getElementById('test-result');
    clearNode(box);
    box.hidden = false;
    const p = document.createElement('p');
    p.className = type === 'ok' ? 'result-ok' : 'result-erro';
    p.textContent = msg;
    box.appendChild(p);
  }

  function showTestLines(lines) {
    const box = document.getElementById('test-result');
    const pre = document.createElement('pre');
    pre.className = 'receipt-preview';
    pre.textContent = lines.join('\n');
    box.appendChild(pre);
  }

  async function runTest() {
    const box = document.getElementById('test-result');
    clearNode(box);
    box.hidden = false;
    const p = document.createElement('p');
    p.textContent = 'Enviando teste...';
    box.appendChild(p);
    try {
      const result = await apiFetch(API_TEST, { method: 'POST' });
      clearNode(box);
      const status = document.createElement('p');
      status.className = result.printed ? 'result-ok' : 'result-erro';
      if (result.printed) {
        status.textContent =
          'OK: enviado para ' + result.backend + '. Confira o papel.';
      } else {
        status.textContent =
          'Falhou (' + result.backend + '): ' + (result.print_error || 'erro desconhecido');
      }
      box.appendChild(status);
      if (result.lines && result.lines.length) {
        const label = document.createElement('p');
        label.className = 'hint';
        label.textContent = 'Conteudo enviado:';
        box.appendChild(label);
        showTestLines(result.lines);
      }
    } catch (err) {
      showResult('Erro: ' + err.message, 'erro');
    }
  }

  async function doLogout() {
    try {
      await fetch('/auth/logout', {
        method: 'POST',
        headers: { 'X-CSRF-Token': readCookie('csrf_token') },
      });
    } catch (_) { }
    window.location.assign('/login');
  }

  document.addEventListener('DOMContentLoaded', () => {
    document.getElementById('form-printer').addEventListener('submit', saveSettings);
    document.getElementById('field-backend').addEventListener('change', updateVisibility);
    document.getElementById('btn-test').addEventListener('click', runTest);
    document.getElementById('btn-sair').addEventListener('click', doLogout);
    loadSettings();
  });
})();
