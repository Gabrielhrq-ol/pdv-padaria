/* Gestao de usuarios (Fase 13). Admin only. */

(function () {
  'use strict';

  const API = '/api/admin/users';

  let users = [];
  let currentUser = null;  // user logado, descoberto via "quem sou eu"
  let editingId = null;

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
      const err = new Error(msg);
      err.status = resp.status;
      throw err;
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

  // ---------- load ----------

  async function loadUsers() {
    const tbody = document.getElementById('tbody-users');
    const vazio = document.getElementById('users-vazio');
    clearNode(tbody);
    try {
      users = await apiFetch(API);
    } catch (err) {
      showFeedback('Erro: ' + err.message, 'erro');
      return;
    }

    // Descobre quem sou eu pelo header (user.name no template vem via jinja)
    const headerName = (document.querySelector('.nk-topbar-user strong') || {}).textContent || '';
    currentUser = users.find(u => u.name === headerName.trim()) || null;

    if (!users.length) { vazio.hidden = false; return; }
    vazio.hidden = true;

    users.forEach(u => {
      const tr = document.createElement('tr');
      if (!u.active) tr.classList.add('inativo');

      tr.appendChild(cell(u.name));
      tr.appendChild(cell(u.username));

      // Papel: badge colorido
      const tdRole = document.createElement('td');
      const roleBadge = document.createElement('span');
      roleBadge.className = 'badge ' + (u.role === 'admin' ? 'badge-estorno' : 'badge-entrada');
      roleBadge.textContent = u.role;
      tdRole.appendChild(roleBadge);
      tr.appendChild(tdRole);

      // Status
      const tdStatus = document.createElement('td');
      const statusBadge = document.createElement('span');
      statusBadge.className = 'badge ' + (u.active ? 'badge-entrada' : 'badge-perda');
      statusBadge.textContent = u.active ? 'ativo' : 'inativo';
      tdStatus.appendChild(statusBadge);
      tr.appendChild(tdStatus);

      tr.appendChild(cell(formatDate(u.last_login_at)));

      // Acoes
      const tdActions = document.createElement('td');
      tdActions.className = 'actions';

      const btnEdit = document.createElement('button');
      btnEdit.type = 'button';
      btnEdit.className = 'btn btn-sm';
      btnEdit.textContent = 'Editar';
      btnEdit.addEventListener('click', () => openEdit(u));
      tdActions.appendChild(btnEdit);

      const btnPwd = document.createElement('button');
      btnPwd.type = 'button';
      btnPwd.className = 'btn btn-sm';
      btnPwd.textContent = 'Senha';
      btnPwd.addEventListener('click', () => openPwd(u));
      tdActions.appendChild(btnPwd);

      const isMe = currentUser && currentUser.id === u.id;
      const btnToggle = document.createElement('button');
      btnToggle.type = 'button';
      btnToggle.className = 'btn btn-sm ' + (u.active ? 'btn-danger' : 'btn-primary');
      btnToggle.textContent = u.active ? 'Desativar' : 'Ativar';
      if (isMe && u.active) {
        btnToggle.disabled = true;
        btnToggle.title = 'Admin nao pode desativar a si mesmo';
      }
      btnToggle.addEventListener('click', () => toggleActive(u));
      tdActions.appendChild(btnToggle);

      tr.appendChild(tdActions);
      tbody.appendChild(tr);
    });
  }

  // ---------- novo / editar ----------

  function openNew() {
    editingId = null;
    document.getElementById('user-modal-title').textContent = 'Novo usuario';
    document.getElementById('user-id').value = '';
    document.getElementById('user-name').value = '';
    document.getElementById('user-username').value = '';
    document.getElementById('user-username').disabled = false;
    document.getElementById('user-role').value = 'caixa';
    document.getElementById('user-password').value = '';
    document.getElementById('row-password-create').hidden = false;
    document.getElementById('user-password').required = true;
    showError('user-erro', null);
    document.getElementById('modal-user').hidden = false;
    setTimeout(() => document.getElementById('user-name').focus(), 10);
  }

  function openEdit(u) {
    editingId = u.id;
    document.getElementById('user-modal-title').textContent = 'Editar usuario';
    document.getElementById('user-id').value = String(u.id);
    document.getElementById('user-name').value = u.name;
    document.getElementById('user-username').value = u.username;
    document.getElementById('user-username').disabled = true;
    document.getElementById('user-role').value = u.role;
    document.getElementById('user-password').value = '';
    document.getElementById('row-password-create').hidden = true;
    document.getElementById('user-password').required = false;
    showError('user-erro', null);
    document.getElementById('modal-user').hidden = false;
    setTimeout(() => document.getElementById('user-name').focus(), 10);
  }

  async function submitUser(ev) {
    ev.preventDefault();
    showError('user-erro', null);
    const name = document.getElementById('user-name').value.trim();
    const username = document.getElementById('user-username').value.trim();
    const role = document.getElementById('user-role').value;

    try {
      if (editingId == null) {
        const password = document.getElementById('user-password').value;
        await apiFetch(API, {
          method: 'POST',
          body: JSON.stringify({ name, username, password, role }),
        });
        showFeedback('Usuario criado.', 'ok');
      } else {
        await apiFetch(API + '/' + editingId, {
          method: 'PUT',
          body: JSON.stringify({ name, role }),
        });
        showFeedback('Usuario atualizado.', 'ok');
      }
      closeModal('modal-user');
      await loadUsers();
    } catch (err) {
      showError('user-erro', err.message);
    }
  }

  // ---------- trocar senha ----------

  function openPwd(u) {
    document.getElementById('pwd-user-id').value = String(u.id);
    document.getElementById('pwd-user-name').textContent = u.name + ' (' + u.username + ')';
    document.getElementById('pwd-new').value = '';
    showError('pwd-erro', null);
    document.getElementById('modal-pwd').hidden = false;
    setTimeout(() => document.getElementById('pwd-new').focus(), 10);
  }

  async function submitPwd(ev) {
    ev.preventDefault();
    showError('pwd-erro', null);
    const id = document.getElementById('pwd-user-id').value;
    const new_password = document.getElementById('pwd-new').value;
    try {
      await apiFetch(API + '/' + id + '/change-password', {
        method: 'POST',
        body: JSON.stringify({ new_password }),
      });
      showFeedback('Senha trocada.', 'ok');
      closeModal('modal-pwd');
    } catch (err) {
      showError('pwd-erro', err.message);
    }
  }

  // ---------- toggle active ----------

  async function toggleActive(u) {
    const action = u.active ? 'desativar' : 'ativar';
    if (!confirm('Confirma ' + action + ' ' + u.name + '?')) return;
    try {
      await apiFetch(API + '/' + u.id + '/toggle-active', {
        method: 'POST',
        body: JSON.stringify({ active: !u.active }),
      });
      showFeedback('Usuario ' + (u.active ? 'desativado' : 'ativado') + '.', 'ok');
      await loadUsers();
    } catch (err) {
      showFeedback('Erro: ' + err.message, 'erro');
    }
  }

  // ---------- modal control ----------

  function closeModal(id) {
    const m = document.getElementById(id);
    if (m) m.hidden = true;
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
    document.getElementById('btn-novo').addEventListener('click', openNew);
    document.getElementById('form-user').addEventListener('submit', submitUser);
    document.getElementById('form-pwd').addEventListener('submit', submitPwd);
    document.getElementById('btn-sair').addEventListener('click', doLogout);

    document.querySelectorAll('[data-close]').forEach(b => {
      b.addEventListener('click', () => closeModal(b.dataset.close));
    });
    ['modal-user', 'modal-pwd'].forEach(id => {
      const m = document.getElementById(id);
      m.addEventListener('click', (ev) => { if (ev.target === m) closeModal(id); });
    });

    loadUsers();
  });
})();
