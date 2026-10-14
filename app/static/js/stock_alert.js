/*
  Alerta de estoque baixo. Procura #btn-low-stock + #low-stock-count +
  #modal-low-stock. Nao faz nada se os elementos nao existirem.
*/

(function () {
  'use strict';

  const API_LOW = '/api/admin/stock/low';

  function formatQty(milli, unit) {
    const sign = milli < 0 ? '-' : '';
    const abs = Math.abs(milli | 0);
    const inteiro = Math.floor(abs / 1000);
    const resto = (abs % 1000).toString().padStart(3, '0');
    if (unit === 'UN' && abs % 1000 === 0) return sign + String(abs / 1000);
    return sign + inteiro + ',' + resto;
  }

  async function fetchLow() {
    try {
      const resp = await fetch(API_LOW, { headers: { 'Accept': 'application/json' } });
      if (!resp.ok) return [];
      return await resp.json();
    } catch (_) {
      return [];
    }
  }

  function updateCounter(rows) {
    const btn = document.getElementById('btn-low-stock');
    const count = document.getElementById('low-stock-count');
    if (!btn || !count) return;
    count.textContent = String(rows.length);
    btn.hidden = rows.length === 0;
  }

  function renderTable(rows) {
    const tbody = document.getElementById('tbody-low-stock');
    const vazio = document.getElementById('low-stock-vazio');
    if (!tbody) return;
    while (tbody.firstChild) tbody.removeChild(tbody.firstChild);
    if (!rows || rows.length === 0) {
      if (vazio) vazio.hidden = false;
      return;
    }
    if (vazio) vazio.hidden = true;
    rows.forEach(r => {
      const tr = document.createElement('tr');
      const tdName = document.createElement('td');
      tdName.textContent = r.product_name;
      tr.appendChild(tdName);
      const tdUnit = document.createElement('td');
      tdUnit.textContent = r.unit;
      tr.appendChild(tdUnit);
      const tdSaldo = document.createElement('td');
      tdSaldo.className = 'num';
      tdSaldo.textContent = formatQty(r.stock_milli, r.unit);
      tr.appendChild(tdSaldo);
      const tdMin = document.createElement('td');
      tdMin.className = 'num';
      tdMin.textContent = formatQty(r.min_stock_milli, r.unit);
      tr.appendChild(tdMin);
      tbody.appendChild(tr);
    });
  }

  function openModal(rows) {
    const modal = document.getElementById('modal-low-stock');
    if (!modal) return;
    renderTable(rows);
    modal.hidden = false;
  }

  function closeModal() {
    const modal = document.getElementById('modal-low-stock');
    if (modal) modal.hidden = true;
  }

  document.addEventListener('DOMContentLoaded', async () => {
    const btn = document.getElementById('btn-low-stock');
    if (!btn) return;
    let rows = await fetchLow();
    updateCounter(rows);

    btn.addEventListener('click', async () => {
      rows = await fetchLow();
      updateCounter(rows);
      openModal(rows);
    });
    const closeBtn = document.getElementById('btn-fechar-low-stock');
    if (closeBtn) closeBtn.addEventListener('click', closeModal);
    const modal = document.getElementById('modal-low-stock');
    if (modal) {
      modal.addEventListener('click', (ev) => {
        if (ev.target === modal) closeModal();
      });
    }
  });
})();
