/*
  Fase 18: dropdown de operador no PDV (sem senha).
  Lista users ativos, grava cookie operator_id ao escolher.
*/

(function () {
  'use strict';

  const API_OPERATORS = '/api/pdv/operators';
  const API_CURRENT = '/api/pdv/current-operator';
  const API_SELECT = '/api/pdv/select-operator';

  let operators = [];
  let currentOp = null;

  async function fetchJson(path, options) {
    const opts = Object.assign({
      headers: { 'Accept': 'application/json', 'Content-Type': 'application/json' },
    }, options || {});
    const r = await fetch(path, opts);
    const body = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(body.detail || r.statusText);
    return body;
  }

  async function loadCurrent() {
    try {
      const r = await fetchJson(API_CURRENT);
      currentOp = r.operator;
      renderCurrent();
    } catch (_) {}
  }

  async function loadOperators() {
    try {
      operators = await fetchJson(API_OPERATORS);
    } catch (_) { operators = []; }
  }

  function renderCurrent() {
    const nameEl = document.getElementById('operator-name');
    if (!nameEl) return;
    if (currentOp) {
      nameEl.textContent = currentOp.name.split(' ')[0]; // primeiro nome
    } else {
      nameEl.textContent = 'Trocar';
    }
  }

  function renderMenu() {
    const menu = document.getElementById('operator-menu');
    if (!menu) return;
    while (menu.firstChild) menu.removeChild(menu.firstChild);
    if (!operators.length) {
      const p = document.createElement('div');
      p.className = 'operator-menu-empty';
      p.textContent = 'Nenhum operador cadastrado. Peca pro dono criar em /admin/usuarios.';
      menu.appendChild(p);
      return;
    }
    operators.forEach(op => {
      const item = document.createElement('button');
      item.type = 'button';
      item.className = 'operator-menu-item';
      if (currentOp && currentOp.id === op.id) item.classList.add('selected');
      const name = document.createElement('strong');
      name.textContent = op.name;
      item.appendChild(name);
      const role = document.createElement('span');
      role.className = 'operator-menu-role';
      role.textContent = op.role;
      item.appendChild(role);
      item.addEventListener('click', () => selectOperator(op));
      menu.appendChild(item);
    });
  }

  async function selectOperator(op) {
    try {
      const r = await fetchJson(API_SELECT, {
        method: 'POST',
        body: JSON.stringify({ operator_id: op.id }),
      });
      currentOp = r.operator;
      renderCurrent();
      closeMenu();
      // feedback leve
      if (window.showPdvToast) window.showPdvToast('Boa venda, ' + op.name.split(' ')[0] + '!', 'ok');
    } catch (err) {
      alert('Erro ao selecionar operador: ' + err.message);
    }
  }

  function openMenu() {
    const menu = document.getElementById('operator-menu');
    if (!menu) return;
    renderMenu();
    menu.hidden = false;
    document.addEventListener('click', outsideClick, { capture: true });
  }

  function closeMenu() {
    const menu = document.getElementById('operator-menu');
    if (menu) menu.hidden = true;
    document.removeEventListener('click', outsideClick, { capture: true });
  }

  function outsideClick(ev) {
    const sel = document.querySelector('.operator-selector');
    if (sel && !sel.contains(ev.target)) closeMenu();
  }

  document.addEventListener('DOMContentLoaded', async () => {
    const btn = document.getElementById('btn-operator');
    if (!btn) return;
    btn.addEventListener('click', (ev) => {
      ev.stopPropagation();
      const menu = document.getElementById('operator-menu');
      if (menu.hidden) openMenu();
      else closeMenu();
    });
    await loadOperators();
    await loadCurrent();
  });
})();
