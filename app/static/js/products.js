/*
  PDV Padaria - frontend de produtos.
  REGRA: NUNCA usar innerHTML com dado vindo do backend ou do usuario.
  Usar textContent / createElement sempre.
*/

(function () {
  'use strict';

  const API = '/api/products';

  // ---------- utilidades de formato ----------

  function formatCents(cents) {
    if (cents === null || cents === undefined) return '-';
    const neg = cents < 0;
    const abs = Math.abs(cents);
    const reais = Math.floor(abs / 100);
    const cent = abs % 100;
    const reaisStr = reais.toString().replace(/\B(?=(\d{3})+(?!\d))/g, '.');
    const centStr = cent.toString().padStart(2, '0');
    return (neg ? '-R$ ' : 'R$ ') + reaisStr + ',' + centStr;
  }

  function formatQty(milli, unit) {
    if (milli === null || milli === undefined) return '-';
    if (unit === 'UN' && milli % 1000 === 0) {
      return (milli / 1000).toString();
    }
    const inteiro = Math.floor(milli / 1000);
    const resto = milli % 1000;
    return inteiro.toString() + ',' + resto.toString().padStart(3, '0');
  }

  // Converte "18,00" ou "18.00" para centavos (int). Retorna null se vazio.
  function parseBRL(text) {
    if (text === null || text === undefined) return null;
    const trimmed = text.toString().trim();
    if (trimmed === '') return null;
    if (trimmed.startsWith('-')) throw new Error('Valor nao pode ser negativo.');
    const cleaned = trimmed.replace(/^R\$\s*/i, '');
    // Detecta separador decimal: ultimo entre , e .
    const lastComma = cleaned.lastIndexOf(',');
    const lastDot = cleaned.lastIndexOf('.');
    let integerPart;
    let decimalPart;
    if (lastComma === -1 && lastDot === -1) {
      if (!/^\d+$/.test(cleaned)) throw new Error('Valor invalido.');
      integerPart = cleaned;
      decimalPart = '';
    } else {
      let decimalSep;
      let thousandSep;
      if (lastComma > lastDot) {
        decimalSep = ',';
        thousandSep = '.';
      } else {
        decimalSep = '.';
        thousandSep = ',';
      }
      const idx = cleaned.lastIndexOf(decimalSep);
      integerPart = cleaned.slice(0, idx).split(thousandSep).join('');
      decimalPart = cleaned.slice(idx + 1);
      if (!/^\d+$/.test(integerPart) || !/^\d*$/.test(decimalPart)) {
        throw new Error('Valor invalido.');
      }
      if (decimalPart.length > 2) throw new Error('Mais de 2 casas decimais.');
    }
    decimalPart = (decimalPart + '00').slice(0, 2);
    return parseInt(integerPart, 10) * 100 + parseInt(decimalPart, 10);
  }

  // Converte "0,350" para milesimos (int). unit influencia casas aceitas.
  function parseQty(text, unit) {
    if (text === null || text === undefined) return null;
    const trimmed = text.toString().trim();
    if (trimmed === '') return 0;
    if (trimmed.startsWith('-')) throw new Error('Quantidade nao pode ser negativa.');
    const normalized = trimmed.replace('.', ',');
    let integerPart;
    let decimalPart;
    if (normalized.indexOf(',') >= 0) {
      const parts = normalized.split(',');
      integerPart = parts[0] || '0';
      decimalPart = parts[1] || '';
    } else {
      integerPart = normalized;
      decimalPart = '';
    }
    if (!/^\d+$/.test(integerPart) || !/^\d*$/.test(decimalPart)) {
      throw new Error('Quantidade invalida.');
    }
    if (decimalPart.length > 3) throw new Error('Maximo 3 casas decimais.');
    decimalPart = (decimalPart + '000').slice(0, 3);
    return parseInt(integerPart, 10) * 1000 + parseInt(decimalPart, 10);
  }

  // ---------- feedback / erros ----------

  function showFeedback(msg, ok) {
    const el = document.getElementById('feedback');
    el.textContent = msg || '';
    el.className = 'feedback ' + (ok ? 'ok' : 'erro');
    if (msg) {
      setTimeout(() => {
        if (el.textContent === msg) {
          el.textContent = '';
          el.className = 'feedback';
        }
      }, 4000);
    }
  }

  function showFormError(msg) {
    const el = document.getElementById('erro-form');
    if (!msg) {
      el.hidden = true;
      el.textContent = '';
    } else {
      el.hidden = false;
      el.textContent = msg;
    }
  }

  // ---------- fetch wrapper ----------

  async function apiFetch(path, options) {
    const resp = await fetch(path, Object.assign({
      headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
    }, options || {}));
    const contentType = resp.headers.get('content-type') || '';
    const isJson = contentType.indexOf('application/json') >= 0;
    const body = isJson ? await resp.json() : await resp.text();
    if (!resp.ok) {
      let msg = (body && body.detail) || resp.statusText || 'Erro.';
      if (body && Array.isArray(body.errors)) {
        const details = body.errors.map(e => e.msg + ' (' + (e.loc || []).join('.') + ')').join('\n');
        msg = (msg + '\n' + details).trim();
      }
      const err = new Error(msg);
      err.status = resp.status;
      throw err;
    }
    return body;
  }

  // ---------- render ----------

  function clearTbody() {
    const tbody = document.getElementById('tbody-produtos');
    while (tbody.firstChild) tbody.removeChild(tbody.firstChild);
  }

  function appendCell(row, text, cssClass) {
    const td = document.createElement('td');
    td.textContent = text === null || text === undefined || text === '' ? '-' : text;
    if (cssClass) td.className = cssClass;
    row.appendChild(td);
  }

  function appendBoolCell(row, value) {
    const td = document.createElement('td');
    td.textContent = value ? 'Sim' : 'Nao';
    row.appendChild(td);
  }

  function appendActions(row, product) {
    const td = document.createElement('td');
    td.className = 'actions';
    const btnEdit = document.createElement('button');
    btnEdit.type = 'button';
    btnEdit.className = 'btn btn-sm';
    btnEdit.textContent = 'Editar';
    btnEdit.addEventListener('click', () => openModal(product));
    td.appendChild(btnEdit);

    const btnToggle = document.createElement('button');
    btnToggle.type = 'button';
    btnToggle.className = 'btn btn-sm' + (product.active ? ' btn-danger' : '');
    btnToggle.textContent = product.active ? 'Desativar' : 'Reativar';
    btnToggle.style.marginLeft = '6px';
    btnToggle.addEventListener('click', () => toggleActive(product));
    td.appendChild(btnToggle);

    row.appendChild(td);
  }

  function renderProducts(products) {
    clearTbody();
    const empty = document.getElementById('tabela-vazia');
    if (!products.length) {
      empty.hidden = false;
      return;
    }
    empty.hidden = true;
    const tbody = document.getElementById('tbody-produtos');
    products.forEach(p => {
      const row = document.createElement('tr');
      if (!p.active) row.classList.add('inativo');
      appendCell(row, p.name);
      appendCell(row, p.barcode);
      appendCell(row, p.internal_code);
      appendCell(row, p.unit);
      appendCell(row, formatCents(p.price_cents), 'num');
      appendCell(row, formatQty(p.stock_milli, p.unit), 'num');
      appendBoolCell(row, p.active);
      appendBoolCell(row, p.favorite);
      appendActions(row, p);
      tbody.appendChild(row);
    });
  }

  // ---------- carregamento ----------

  async function loadProducts() {
    const q = document.getElementById('busca').value.trim();
    const includeInactive = document.getElementById('chk-inativos').checked;
    const params = new URLSearchParams();
    if (includeInactive) params.set('include_inactive', 'true');
    try {
      let list;
      if (q) {
        params.set('q', q);
        list = await apiFetch(API + '/search?' + params.toString());
      } else {
        list = await apiFetch(API + (params.toString() ? '?' + params.toString() : ''));
      }
      renderProducts(list);
    } catch (err) {
      showFeedback('Erro ao carregar produtos: ' + err.message, false);
    }
  }

  // ---------- modal ----------

  function openModal(product) {
    const modal = document.getElementById('modal-produto');
    const titulo = document.getElementById('modal-titulo');
    showFormError(null);
    document.getElementById('form-produto').reset();
    document.getElementById('field-id').value = '';
    if (product) {
      titulo.textContent = 'Editar produto';
      document.getElementById('field-id').value = String(product.id);
      document.getElementById('field-name').value = product.name;
      document.getElementById('field-barcode').value = product.barcode || '';
      document.getElementById('field-internal_code').value = product.internal_code || '';
      document.getElementById('field-unit').value = product.unit;
      document.getElementById('field-price').value = formatCents(product.price_cents).replace(/^R\$\s*/, '');
      document.getElementById('field-cost').value =
        product.cost_cents === null || product.cost_cents === undefined
          ? ''
          : formatCents(product.cost_cents).replace(/^R\$\s*/, '');
      document.getElementById('field-stock').value = formatQty(product.stock_milli, product.unit);
      document.getElementById('field-min_stock').value = formatQty(product.min_stock_milli, product.unit);
      document.getElementById('field-favorite').checked = !!product.favorite;
    } else {
      titulo.textContent = 'Novo produto';
      document.getElementById('field-unit').value = 'UN';
    }
    modal.hidden = false;
    setTimeout(() => document.getElementById('field-name').focus(), 50);
  }

  function closeModal() {
    document.getElementById('modal-produto').hidden = true;
    showFormError(null);
  }

  function readForm() {
    const unit = document.getElementById('field-unit').value;
    const payload = {
      name: document.getElementById('field-name').value.trim(),
      barcode: document.getElementById('field-barcode').value.trim() || null,
      internal_code: document.getElementById('field-internal_code').value.trim() || null,
      unit: unit,
      price_cents: parseBRL(document.getElementById('field-price').value),
      cost_cents: parseBRL(document.getElementById('field-cost').value),
      stock_milli: parseQty(document.getElementById('field-stock').value, unit),
      min_stock_milli: parseQty(document.getElementById('field-min_stock').value, unit),
      favorite: document.getElementById('field-favorite').checked,
    };
    if (payload.price_cents === null) throw new Error('Preco e obrigatorio.');
    if (payload.stock_milli === null) payload.stock_milli = 0;
    if (payload.min_stock_milli === null) payload.min_stock_milli = 0;
    return payload;
  }

  async function submitForm(ev) {
    ev.preventDefault();
    showFormError(null);
    let payload;
    try {
      payload = readForm();
    } catch (err) {
      showFormError(err.message);
      return;
    }
    const id = document.getElementById('field-id').value;
    try {
      if (id) {
        await apiFetch(API + '/' + encodeURIComponent(id), {
          method: 'PUT',
          body: JSON.stringify(payload),
        });
        showFeedback('Produto atualizado.', true);
      } else {
        await apiFetch(API, {
          method: 'POST',
          body: JSON.stringify(payload),
        });
        showFeedback('Produto cadastrado.', true);
      }
      closeModal();
      loadProducts();
    } catch (err) {
      showFormError(err.message);
    }
  }

  async function toggleActive(product) {
    const want = !product.active;
    const label = want ? 'reativar' : 'desativar';
    if (!confirm('Deseja ' + label + ' "' + product.name + '"?')) return;
    try {
      await apiFetch(API + '/' + product.id + '/active', {
        method: 'PATCH',
        body: JSON.stringify({ active: want }),
      });
      showFeedback('Produto ' + (want ? 'reativado' : 'desativado') + '.', true);
      loadProducts();
    } catch (err) {
      showFeedback('Erro: ' + err.message, false);
    }
  }

  // ---------- bindings ----------

  function debounce(fn, delay) {
    let t;
    return function () {
      const args = arguments;
      clearTimeout(t);
      t = setTimeout(() => fn.apply(null, args), delay);
    };
  }

  document.addEventListener('DOMContentLoaded', () => {
    document.getElementById('btn-novo').addEventListener('click', () => openModal(null));
    document.getElementById('btn-fechar-modal').addEventListener('click', closeModal);
    document.getElementById('btn-cancelar').addEventListener('click', closeModal);
    document.getElementById('form-produto').addEventListener('submit', submitForm);
    document.getElementById('busca').addEventListener('input', debounce(loadProducts, 250));
    document.getElementById('chk-inativos').addEventListener('change', loadProducts);
    document.addEventListener('keydown', (ev) => {
      if (ev.key === 'Escape' && !document.getElementById('modal-produto').hidden) {
        closeModal();
      }
    });
    loadProducts();
  });
})();
