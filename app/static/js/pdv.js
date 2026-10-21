/*
  PDV (Fase 3): montagem de venda via teclado + leitor.
  REGRA: nunca innerHTML com dado do backend/usuario.
*/

(function () {
  'use strict';

  const API_SALES = '/api/sales';
  const API_PRODUCTS = '/api/products';

  let currentSale = null;      // {id, number, items, total_cents, ...}
  let selectedIndex = -1;      // indice do item destacado
  let allProducts = [];        // cache de produtos (favoritos + busca)

  // ---------- formato ----------

  function formatCents(cents) {
    if (cents === null || cents === undefined) return '-';
    const neg = cents < 0;
    const abs = Math.abs(cents);
    const reais = Math.floor(abs / 100);
    const cent = abs % 100;
    const reaisStr = reais.toString().replace(/\B(?=(\d{3})+(?!\d))/g, '.');
    return (neg ? '-R$ ' : 'R$ ') + reaisStr + ',' + cent.toString().padStart(2, '0');
  }

  function formatQty(milli, unit) {
    if (milli === null || milli === undefined) return '-';
    if (unit === 'UN' && milli % 1000 === 0) {
      return (milli / 1000).toString() + ' UN';
    }
    const inteiro = Math.floor(milli / 1000);
    const resto = milli % 1000;
    const suffix = unit === 'UN' ? '' : ' ' + unit.toLowerCase();
    return inteiro.toString() + ',' + resto.toString().padStart(3, '0') + suffix;
  }

  function parseQty(text, unit) {
    const trimmed = (text || '').toString().trim().replace('.', ',');
    if (!trimmed) throw new Error('Quantidade vazia.');
    if (trimmed.startsWith('-')) throw new Error('Quantidade negativa.');
    let integer, decimal;
    if (trimmed.indexOf(',') >= 0) {
      const parts = trimmed.split(',');
      integer = parts[0] || '0';
      decimal = parts[1] || '';
    } else {
      integer = trimmed; decimal = '';
    }
    if (!/^\d+$/.test(integer) || !/^\d*$/.test(decimal)) throw new Error('Quantidade invalida.');
    if (decimal.length > 3) throw new Error('Max 3 casas decimais.');
    decimal = (decimal + '000').slice(0, 3);
    return parseInt(integer, 10) * 1000 + parseInt(decimal, 10);
  }

  // ---------- CSRF + fetch ----------

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
    if (method !== 'GET' && method !== 'HEAD' && method !== 'OPTIONS') {
      opts.headers['X-CSRF-Token'] = readCookie('csrf_token');
    }
    const resp = await fetch(path, opts);
    if (resp.status === 401) {
      window.location.assign('/login');
      throw new Error('Nao autenticado.');
    }
    const ct = resp.headers.get('content-type') || '';
    const body = ct.indexOf('application/json') >= 0 ? await resp.json() : await resp.text();
    if (!resp.ok) {
      let msg = (body && body.detail) || resp.statusText || 'Erro.';
      if (body && Array.isArray(body.errors)) {
        msg = msg + '\n' + body.errors.map(e => e.msg).join('\n');
      }
      const err = new Error(msg);
      err.status = resp.status;
      throw err;
    }
    return body;
  }

  // ---------- feedback / toast / beep ----------

  function setFeedback(msg, cls) {
    const el = document.getElementById('pdv-feedback');
    el.textContent = msg || '';
    el.className = 'pdv-feedback' + (cls ? ' ' + cls : '');
    if (msg) {
      setTimeout(() => {
        if (el.textContent === msg) {
          el.textContent = ''; el.className = 'pdv-feedback';
        }
      }, 2500);
    }
  }

  function showToast(msg, cls) {
    const el = document.getElementById('pdv-toast');
    el.textContent = msg;
    el.className = 'pdv-toast' + (cls ? ' ' + cls : '');
    el.hidden = false;
    clearTimeout(showToast._t);
    showToast._t = setTimeout(() => { el.hidden = true; }, 2000);
  }

  function beepErro() {
    try {
      const ctx = new (window.AudioContext || window.webkitAudioContext)();
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.frequency.value = 180;
      osc.connect(gain); gain.connect(ctx.destination);
      gain.gain.value = 0.05;
      osc.start(); osc.stop(ctx.currentTime + 0.15);
    } catch (_) { /* no-op */ }
  }

  // ---------- render ----------

  function clearNode(el) {
    while (el.firstChild) el.removeChild(el.firstChild);
  }

  function appendCell(row, text, cls) {
    const td = document.createElement('td');
    td.textContent = text == null || text === '' ? '-' : text;
    if (cls) td.className = cls;
    row.appendChild(td);
  }

  function renderCurrentProduct(item) {
    // Painel estilo Onix: 4 barras brancas com nome/preco/qtd/total.
    // item == null => campos vazios + rodape "PASSE O PRODUTO"
    const nameEl = document.getElementById('current-product-name');
    const unitEl = document.getElementById('current-unit-price');
    const qtyEl = document.getElementById('current-qty');
    const totalEl = document.getElementById('current-line-total');
    const actionLabel = document.getElementById('onix-action-label');
    if (!nameEl) return;
    if (!item) {
      nameEl.innerHTML = '&nbsp;';
      unitEl.innerHTML = '&nbsp;';
      qtyEl.innerHTML = '&nbsp;';
      totalEl.innerHTML = '&nbsp;';
      if (actionLabel) actionLabel.textContent = 'PASSE O PRODUTO';
      return;
    }
    nameEl.textContent = item.product_name;
    unitEl.textContent = formatCents(item.unit_price_cents);
    qtyEl.textContent = formatQty(item.qty_milli, item.unit) + (item.unit !== 'UN' ? ' ' + item.unit : '');
    totalEl.textContent = formatCents(item.line_total_cents);
    if (actionLabel) actionLabel.textContent = 'VENDA EM ANDAMENTO';
  }

  function renderSale() {
    const number = document.getElementById('sale-number');
    const list = document.getElementById('cupom-list');
    const empty = document.getElementById('pdv-empty');
    const total = document.getElementById('pdv-total');
    const countEl = document.getElementById('cupom-count');

    clearNode(list);

    if (!currentSale) {
      number.textContent = '—';
      total.textContent = 'R$ 0,00';
      if (countEl) countEl.textContent = '0 itens';
      if (empty) { list.appendChild(empty); empty.hidden = false; }
      renderCurrentProduct(null);
      return;
    }

    number.textContent = String(currentSale.number).padStart(6, '0');
    total.textContent = formatCents(currentSale.total_cents);

    const items = currentSale.items || [];
    if (countEl) countEl.textContent = items.length + (items.length === 1 ? ' item' : ' itens');

    if (items.length === 0) {
      if (empty) { list.appendChild(empty); empty.hidden = false; }
      renderCurrentProduct(null);
      return;
    }

    // Lista estilo mini-cupom (sem tabela)
    items.forEach((it, idx) => {
      const row = document.createElement('div');
      row.className = 'cupom-row';
      row.dataset.itemId = String(it.id);
      row.dataset.unit = it.unit;
      if (idx === selectedIndex) row.classList.add('selected');

      const line1 = document.createElement('div');
      line1.className = 'cupom-row-top';
      const idxEl = document.createElement('span');
      idxEl.className = 'cupom-row-idx';
      idxEl.textContent = String(idx + 1).padStart(3, '0');
      line1.appendChild(idxEl);
      const nameEl = document.createElement('span');
      nameEl.className = 'cupom-row-name';
      nameEl.textContent = it.product_name;
      line1.appendChild(nameEl);
      row.appendChild(line1);

      const line2 = document.createElement('div');
      line2.className = 'cupom-row-bot';
      const qtyPrice = document.createElement('span');
      qtyPrice.className = 'cupom-row-qty';
      qtyPrice.textContent = formatQty(it.qty_milli, it.unit) + '  x  ' + formatCents(it.unit_price_cents);
      line2.appendChild(qtyPrice);
      const t = document.createElement('span');
      t.className = 'cupom-row-total';
      t.textContent = formatCents(it.line_total_cents);
      line2.appendChild(t);
      row.appendChild(line2);

      row.addEventListener('click', () => { selectedIndex = idx; renderSale(); });
      list.appendChild(row);
    });

    // "Produto atual" = selecionado se tiver, senao o ultimo adicionado
    const activeIdx = selectedIndex >= 0 && selectedIndex < items.length ? selectedIndex : items.length - 1;
    renderCurrentProduct(items[activeIdx]);

    // Scroll pro ultimo item
    if (list.lastChild && list.lastChild.scrollIntoView) {
      list.lastChild.scrollIntoView({ block: 'nearest' });
    }
  }

  function renderFavorites() {
    // Fase 14: barra de favoritos no painel esquerdo do PDV.
    const bar = document.getElementById('pdv-favorites-bar');
    if (bar) {
      clearNode(bar);
      const favs = allProducts.filter(p => p.favorite && p.active).slice(0, 12);
      favs.forEach((p, idx) => {
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'fav-btn-market';
        btn.dataset.productId = String(p.id);
        btn.title = p.name + ' - ' + formatCents(p.price_cents) + '/' + p.unit;
        if (idx < 9) {
          const kbd = document.createElement('span');
          kbd.className = 'fav-btn-shortcut';
          kbd.textContent = 'Ctrl+' + (idx + 1);
          btn.appendChild(kbd);
        }
        const nameEl = document.createElement('div');
        nameEl.className = 'fav-btn-name';
        nameEl.textContent = p.name;
        btn.appendChild(nameEl);
        const priceEl = document.createElement('div');
        priceEl.className = 'fav-btn-price';
        priceEl.textContent = formatCents(p.price_cents) + ' / ' + p.unit;
        btn.appendChild(priceEl);
        btn.addEventListener('click', () => addFavorite(p));
        bar.appendChild(btn);
      });
    }
    // Legado: suporta UI antiga se por acaso o container estiver no DOM.
    const box = document.getElementById('pdv-favorites');
    if (!box) return;
    clearNode(box);
    const favs = allProducts.filter(p => p.favorite && p.active);
    favs.forEach(p => {
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'fav-btn';
      const nome = document.createElement('div');
      nome.textContent = p.name;
      btn.appendChild(nome);
      const preco = document.createElement('div');
      preco.className = 'fav-price';
      preco.textContent = formatCents(p.price_cents) + '/' + p.unit;
      btn.appendChild(preco);
      btn.addEventListener('click', () => addFavorite(p));
      box.appendChild(btn);
    });
    if (favs.length === 0) {
      const p = document.createElement('p');
      p.className = 'pdv-empty';
      p.textContent = 'Sem favoritos';
      box.appendChild(p);
    }
  }

  // ---------- venda ----------

  async function ensureSale() {
    if (currentSale && currentSale.status === 'open') return currentSale;
    const open = await apiFetch(API_SALES + '/open');
    if (open) {
      currentSale = open;
      return currentSale;
    }
    currentSale = await apiFetch(API_SALES, { method: 'POST' });
    return currentSale;
  }

  async function addByCode(code) {
    try {
      await ensureSale();
      currentSale = await apiFetch(
        API_SALES + '/' + currentSale.id + '/items',
        { method: 'POST', body: JSON.stringify({ code: code }) }
      );
      selectedIndex = currentSale.items.length - 1;
      renderSale();
      highlightLast();
      setFeedback('OK: ' + currentSale.items[selectedIndex].product_name, 'ok');
    } catch (err) {
      beepErro();
      setFeedback(err.message, 'erro');
    }
  }

  async function addFavorite(product) {
    try {
      await ensureSale();
      let qty = 1000;
      if (product.unit !== 'UN') {
        const typed = prompt('Peso em ' + product.unit + ' (ex: 0,350):');
        if (typed === null) return;
        try { qty = parseQty(typed, product.unit); }
        catch (e) { showToast(e.message, 'erro'); return; }
      }
      currentSale = await apiFetch(
        API_SALES + '/' + currentSale.id + '/items',
        { method: 'POST', body: JSON.stringify({ product_id: product.id, qty_milli: qty }) }
      );
      selectedIndex = currentSale.items.length - 1;
      renderSale();
      highlightLast();
      setFeedback('OK: ' + product.name, 'ok');
    } catch (err) {
      beepErro();
      setFeedback(err.message, 'erro');
    }
  }

  function highlightLast() {
    // UI nova (Fase 12): lista no .cupom-row. Legado: #pdv-tbody tr.
    let rows = document.querySelectorAll('#cupom-list .cupom-row');
    if (!rows.length) rows = document.querySelectorAll('#pdv-tbody tr');
    if (!rows.length) return;
    const last = rows[rows.length - 1];
    last.classList.add('highlight-new');
    setTimeout(() => last.classList.remove('highlight-new'), 1200);
  }

  async function changeQtySelected() {
    if (!currentSale || selectedIndex < 0) {
      showToast('Nenhum item selecionado'); return;
    }
    const item = currentSale.items[selectedIndex];
    document.getElementById('qty-product-info').textContent =
      item.product_name + ' (' + item.unit + ')';
    document.getElementById('qty-input').value = formatQty(item.qty_milli, item.unit).replace(/\s(KG|L|UN)$/i, '').trim();
    openModal('modal-qty');
    document.getElementById('qty-input').focus();
    document.getElementById('qty-input').select();

    document.getElementById('qty-ok').onclick = async () => {
      try {
        const txt = document.getElementById('qty-input').value;
        const qty = parseQty(txt, item.unit);
        currentSale = await apiFetch(
          API_SALES + '/' + currentSale.id + '/items/' + item.id,
          { method: 'PATCH', body: JSON.stringify({ qty_milli: qty }) }
        );
        renderSale();
        closeAllModals();
        setFeedback('Qtd alterada', 'ok');
      } catch (err) {
        showToast(err.message, 'erro');
      }
    };
  }

  async function removeSelected() {
    if (!currentSale || selectedIndex < 0) { showToast('Nenhum item'); return; }
    const item = currentSale.items[selectedIndex];
    if (!confirm('Remover "' + item.product_name + '"?')) return;
    try {
      currentSale = await apiFetch(
        API_SALES + '/' + currentSale.id + '/items/' + item.id,
        { method: 'DELETE' }
      );
      selectedIndex = Math.min(selectedIndex, currentSale.items.length - 1);
      renderSale();
      setFeedback('Item removido', 'ok');
    } catch (err) {
      showToast(err.message, 'erro');
    }
  }

  function openCancelModal() {
    if (!currentSale) { showToast('Nenhuma venda aberta'); return; }
    document.getElementById('cancel-motivo').value = '';
    openModal('modal-cancel');
    document.getElementById('cancel-motivo').focus();

    document.getElementById('cancel-ok').onclick = async () => {
      const motivo = document.getElementById('cancel-motivo').value.trim();
      if (!motivo) { showToast('Motivo obrigatorio', 'erro'); return; }
      try {
        await apiFetch(
          API_SALES + '/' + currentSale.id,
          { method: 'DELETE', body: JSON.stringify({ reason: motivo }) }
        );
        currentSale = null;
        selectedIndex = -1;
        renderSale();
        closeAllModals();
        setFeedback('Venda cancelada', 'ok');
      } catch (err) {
        showToast(err.message, 'erro');
      }
    };
  }

  // ---------- busca F2 ----------

  async function openBusca() {
    openModal('modal-busca');
    document.getElementById('busca-input').value = '';
    document.getElementById('busca-resultado').replaceChildren();
    document.getElementById('busca-input').focus();
  }

  async function doBusca() {
    const q = document.getElementById('busca-input').value.trim();
    const box = document.getElementById('busca-resultado');
    clearNode(box);
    if (!q) return;
    try {
      const results = await apiFetch(API_PRODUCTS + '/search?q=' + encodeURIComponent(q));
      results.forEach(p => {
        const row = document.createElement('div');
        row.className = 'busca-item';
        const nome = document.createElement('span');
        nome.className = 'busca-nome';
        nome.textContent = p.name + ' (' + p.unit + ')';
        row.appendChild(nome);
        const preco = document.createElement('span');
        preco.className = 'busca-preco';
        preco.textContent = formatCents(p.price_cents);
        row.appendChild(preco);
        row.addEventListener('click', () => {
          closeAllModals();
          addFavorite(p);
        });
        box.appendChild(row);
      });
    } catch (err) {
      const p = document.createElement('p');
      p.textContent = 'Erro: ' + err.message;
      box.appendChild(p);
    }
  }

  // ---------- consulta preco F9 ----------

  async function openPreco() {
    openModal('modal-preco');
    document.getElementById('preco-input').value = '';
    document.getElementById('preco-resultado').replaceChildren();
    document.getElementById('preco-input').focus();
  }

  async function doConsultaPreco(code) {
    const box = document.getElementById('preco-resultado');
    clearNode(box);
    if (!code) return;
    try {
      const result = await apiFetch(API_PRODUCTS + '/by-code/' + encodeURIComponent(code));
      const p = result.product;
      const divBox = document.createElement('div');
      divBox.className = 'preco-box';
      const nome = document.createElement('div');
      nome.className = 'preco-nome';
      nome.textContent = p.name + ' (' + p.unit + ')';
      const valor = document.createElement('div');
      valor.className = 'preco-valor';
      valor.textContent = formatCents(p.price_cents);
      const estoque = document.createElement('div');
      estoque.className = 'preco-estoque';
      estoque.textContent = 'Estoque: ' + formatQty(p.stock_milli, p.unit);
      divBox.appendChild(nome); divBox.appendChild(valor); divBox.appendChild(estoque);
      box.appendChild(divBox);
    } catch (err) {
      const p = document.createElement('p');
      p.textContent = err.message;
      box.appendChild(p);
    }
  }

  // ---------- modal pagamento (F6) ----------

  let payState = { payments: [], discount_cents: 0, discount_reason: '' };

  function parseCents(text) {
    const t = (text || '').toString().trim();
    if (!t) return 0;
    if (t.startsWith('-')) throw new Error('Valor negativo.');
    const cleaned = t.replace(/^R\$\s*/i, '');
    const lastComma = cleaned.lastIndexOf(',');
    const lastDot = cleaned.lastIndexOf('.');
    let integer, decimal;
    if (lastComma === -1 && lastDot === -1) {
      if (!/^\d+$/.test(cleaned)) throw new Error('Valor invalido.');
      return parseInt(cleaned, 10) * 100;
    }
    const decimalSep = lastComma > lastDot ? ',' : '.';
    const thousandSep = decimalSep === ',' ? '.' : ',';
    const idx = cleaned.lastIndexOf(decimalSep);
    integer = cleaned.slice(0, idx).split(thousandSep).join('');
    decimal = cleaned.slice(idx + 1);
    if (!/^\d+$/.test(integer) || !/^\d*$/.test(decimal)) throw new Error('Valor invalido.');
    if (decimal.length > 2) throw new Error('Max 2 casas decimais.');
    decimal = (decimal + '00').slice(0, 2);
    return parseInt(integer, 10) * 100 + parseInt(decimal, 10);
  }

  function renderPaymentList() {
    const list = document.getElementById('pay-list');
    clearNode(list);
    payState.payments.forEach((p, idx) => {
      const row = document.createElement('div');
      row.className = 'pay-item';
      const sel = document.createElement('select');
      ['dinheiro', 'debito', 'credito', 'pix', 'outros'].forEach(m => {
        const op = document.createElement('option');
        op.value = m; op.textContent = m.charAt(0).toUpperCase() + m.slice(1);
        if (m === p.method) op.selected = true;
        sel.appendChild(op);
      });
      sel.addEventListener('change', () => { p.method = sel.value; refreshPaymentCalc(); });
      row.appendChild(sel);

      const inp = document.createElement('input');
      inp.type = 'text';
      inp.inputMode = 'decimal';
      inp.placeholder = '0,00';
      inp.value = p.amountStr;
      inp.addEventListener('input', () => { p.amountStr = inp.value; refreshPaymentCalc(); });
      row.appendChild(inp);

      const btn = document.createElement('button');
      btn.type = 'button';
      btn.textContent = 'Remover';
      btn.addEventListener('click', () => {
        payState.payments.splice(idx, 1);
        renderPaymentList();
        refreshPaymentCalc();
      });
      row.appendChild(btn);
      list.appendChild(row);
    });
  }

  function refreshPaymentCalc() {
    const subtotal = currentSale ? currentSale.subtotal_cents : 0;
    document.getElementById('pay-subtotal').textContent = formatCents(subtotal);

    let discount = 0;
    try {
      discount = parseCents(document.getElementById('pay-discount-input').value);
    } catch (_) { discount = 0; }
    if (discount > subtotal) discount = subtotal;
    payState.discount_cents = discount;
    payState.discount_reason = document.getElementById('pay-discount-reason').value.trim();

    const total = Math.max(0, subtotal - discount);
    document.getElementById('pay-total').textContent = formatCents(total);

    let paid = 0;
    payState.payments.forEach(p => {
      try { p.amount_cents = parseCents(p.amountStr); }
      catch (_) { p.amount_cents = 0; }
      paid += p.amount_cents;
    });
    document.getElementById('pay-paid').textContent = formatCents(paid);

    const diff = paid - total;
    const label = document.getElementById('pay-change-label');
    const value = document.getElementById('pay-change');
    const row = value.parentElement;
    if (diff >= 0) {
      label.textContent = 'Troco';
      value.textContent = formatCents(diff);
      row.classList.remove('falta');
    } else {
      label.textContent = 'Falta';
      value.textContent = formatCents(-diff);
      row.classList.add('falta');
    }
  }

  function openPagamento() {
    if (!currentSale || !currentSale.items || currentSale.items.length === 0) {
      showToast('Nenhum item na venda'); return;
    }
    payState = {
      payments: [{ method: 'dinheiro', amountStr: formatCents(currentSale.subtotal_cents).replace(/^R\$\s*/, '') }],
      discount_cents: 0,
      discount_reason: '',
    };
    document.getElementById('pay-discount-input').value = '';
    document.getElementById('pay-discount-reason').value = '';
    document.getElementById('pay-erro').hidden = true;
    renderPaymentList();
    refreshPaymentCalc();
    openModal('modal-pagamento');
    // Fase 20: foca no primeiro input de valor pra operador digitar direto
    setTimeout(() => {
      const first = document.querySelector('#pay-list input[type="text"]');
      if (first) { first.focus(); first.select(); }
    }, 50);
  }

  // Fase 20: dentro do modal pagamento, teclas 1-5 trocam metodo do primeiro
  // pagamento conforme a lista padrao Onix: 1-dinheiro 2-debito 3-credito 4-pix 5-outros
  function handlePaymentModalKey(ev) {
    const modal = document.getElementById('modal-pagamento');
    if (!modal || modal.hidden) return;
    if (ev.ctrlKey || ev.altKey || ev.metaKey) return;
    if (!/^[1-5]$/.test(ev.key)) return;
    // So dispara se foco nao esta em input (pra nao atrapalhar digitacao de valor)
    const tag = (document.activeElement && document.activeElement.tagName || '').toLowerCase();
    if (tag === 'input' || tag === 'textarea' || tag === 'select') return;
    ev.preventDefault();
    const methods = ['dinheiro', 'debito', 'credito', 'pix', 'outros'];
    const method = methods[parseInt(ev.key, 10) - 1];
    if (!method) return;
    if (payState.payments.length) {
      payState.payments[0].method = method;
      renderPaymentList();
      refreshPaymentCalc();
    }
  }

  async function doFinalize(print_receipt) {
    const erro = document.getElementById('pay-erro');
    erro.hidden = true;
    try {
      refreshPaymentCalc();
      const payments = payState.payments.map(p => ({
        method: p.method, amount_cents: p.amount_cents || 0,
      }));
      const body = {
        payments: payments,
        discount_cents: payState.discount_cents,
        print_receipt: print_receipt,
      };
      if (payState.discount_cents > 0) {
        if (!payState.discount_reason) {
          erro.hidden = false;
          erro.textContent = 'Motivo do desconto e obrigatorio.';
          return;
        }
        body.discount_reason = payState.discount_reason;
      }
      const result = await apiFetch(
        API_SALES + '/' + currentSale.id + '/finalize',
        { method: 'POST', body: JSON.stringify(body) }
      );
      currentSale = null;
      selectedIndex = -1;
      renderSale();
      closeAllModals();
      if (result.printed) {
        setFeedback('Venda finalizada e impressa', 'ok');
      } else if (print_receipt && result.print_error) {
        setFeedback('Venda OK; falha na impressao: ' + result.print_error, 'erro');
      } else {
        setFeedback('Venda finalizada', 'ok');
      }
    } catch (err) {
      erro.hidden = false;
      erro.textContent = err.message;
    }
  }

  async function reprintLast() {
    try {
      const last = await apiFetch(API_SALES + '/last-completed');
      if (!last) { showToast('Nenhuma venda recente para reimprimir'); return; }
      const result = await apiFetch(
        API_SALES + '/' + last.id + '/reprint',
        { method: 'POST' }
      );
      if (result.printed) setFeedback('2a VIA enviada', 'ok');
      else setFeedback('Falha na reimpressao: ' + (result.print_error || ''), 'erro');
    } catch (err) {
      showToast(err.message, 'erro');
    }
  }

  // ---------- modais ----------

  function openModal(id) {
    document.getElementById(id).hidden = false;
  }

  function closeAllModals() {
    ['modal-busca', 'modal-qty', 'modal-preco', 'modal-cancel', 'modal-pagamento'].forEach(id => {
      const el = document.getElementById(id);
      if (el) el.hidden = true;
    });
    document.getElementById('pdv-code').focus();
  }

  // ---------- init ----------

  async function loadProducts() {
    try {
      allProducts = await apiFetch(API_PRODUCTS + '?limit=500');
    } catch (err) {
      showToast('Erro ao carregar produtos: ' + err.message, 'erro');
    }
    renderFavorites();  // no-op se o container nao existir na nova UI
  }

  async function loadOpenSale() {
    try {
      const open = await apiFetch(API_SALES + '/open');
      if (open) {
        currentSale = open;
        selectedIndex = open.items && open.items.length ? open.items.length - 1 : -1;
      }
    } catch (err) {
      showToast('Erro: ' + err.message, 'erro');
    }
    renderSale();
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

  function handleCodeEnter(ev) {
    if (ev.key !== 'Enter') return;
    const input = ev.currentTarget;
    const code = input.value.trim();
    if (!code) {
      // Fase 20: Enter com codigo vazio abre pagamento (padrao Onix).
      ev.preventDefault();
      openPagamento();
      return;
    }
    input.value = '';
    addByCode(code);
  }

  // Fase 20: F1 - MENU FUNCOES. Reusa o modal de operacoes do pdv_operacoes.js.
  function openMenuFuncoes() {
    if (window.PdvOperacoes && window.PdvOperacoes.open) {
      window.PdvOperacoes.open();
    }
  }

  // Fase 20: F11 - CUPOM EM TELA CHEIA (conferencia antes de pagar)
  function openCupomCompleto() {
    const existing = document.getElementById('modal-cupom-full');
    if (existing) existing.remove();

    const items = (currentSale && currentSale.items) || [];
    const modal = document.createElement('div');
    modal.id = 'modal-cupom-full';
    modal.className = 'modal';
    modal.setAttribute('role', 'dialog');
    modal.setAttribute('aria-modal', 'true');
    modal.innerHTML = ''
      + '<div class="modal-content modal-cupom-full-content">'
      +   '<header class="modal-header">'
      +     '<h2>CONFERE O CUPOM</h2>'
      +     '<button type="button" class="btn-close" aria-label="Fechar">x</button>'
      +   '</header>'
      +   '<div class="modal-body cupom-full-body"></div>'
      +   '<footer class="modal-footer cupom-full-footer">'
      +     '<span>TOTAL</span>'
      +     '<strong class="cupom-full-total"></strong>'
      +   '</footer>'
      + '</div>';
    document.body.appendChild(modal);

    const body = modal.querySelector('.cupom-full-body');
    const totalEl = modal.querySelector('.cupom-full-total');
    if (!items.length) {
      const p = document.createElement('p');
      p.className = 'cupom-pane-empty';
      p.textContent = 'Nenhum item passado ainda.';
      body.appendChild(p);
    } else {
      items.forEach((it, idx) => {
        const row = document.createElement('div');
        row.className = 'cupom-full-row';
        const left = document.createElement('div');
        left.className = 'cupom-full-left';
        const name = document.createElement('div');
        name.className = 'cupom-full-name';
        name.textContent = (idx + 1).toString().padStart(3, '0') + '  ' + it.product_name;
        left.appendChild(name);
        const sub = document.createElement('div');
        sub.className = 'cupom-full-sub';
        sub.textContent = formatQty(it.qty_milli, it.unit) + ' ' + it.unit + '  x  ' + formatCents(it.unit_price_cents);
        left.appendChild(sub);
        row.appendChild(left);
        const right = document.createElement('div');
        right.className = 'cupom-full-right';
        right.textContent = formatCents(it.line_total_cents);
        row.appendChild(right);
        body.appendChild(row);
      });
    }
    totalEl.textContent = currentSale ? formatCents(currentSale.total_cents) : 'R$ 0,00';

    modal.querySelector('.btn-close').addEventListener('click', () => modal.remove());
    modal.addEventListener('click', (ev) => { if (ev.target === modal) modal.remove(); });
  }

  function anyModalOpen() {
    return document.querySelector('.modal:not([hidden])') !== null;
  }

  function handleGlobalKey(ev) {
    // Esc OU Tab fecha modais (padrao Onix)
    if (ev.key === 'Escape') { closeAllModals(); return; }
    if (ev.key === 'Tab' && anyModalOpen()) {
      ev.preventDefault();
      closeAllModals();
      return;
    }

    // Teclas de funcao (Fase 20: atalhos pedidos por Gabriel)
    if (ev.key === 'F1') { ev.preventDefault(); openMenuFuncoes(); return; }
    if (ev.key === 'F2') { ev.preventDefault(); openBusca(); return; }
    if (ev.key === 'F3') { ev.preventDefault(); removeSelected(); return; }   // F3 cancela item
    if (ev.key === 'F8') { ev.preventDefault(); openCancelModal(); return; }
    if (ev.key === 'F10') { ev.preventDefault(); reprintLast(); return; }
    if (ev.key === 'F11') { ev.preventDefault(); openCupomCompleto(); return; }

    // F4 e F6 preservados pra compatibilidade com documentacao antiga
    if (ev.key === 'F4') { ev.preventDefault(); removeSelected(); return; }
    if (ev.key === 'F6') { ev.preventDefault(); openPagamento(); return; }
    if (ev.key === 'F9') { ev.preventDefault(); openPreco(); return; }
    if (ev.key === 'F12') {
      ev.preventDefault();
      if (window.PdvOperacoes && window.PdvOperacoes.open) {
        window.PdvOperacoes.open();
      }
      return;
    }

    // H sem modificador = consulta rapida (Fase 20).
    // So dispara se foco nao esta em input/textarea pra nao bloquear digitacao.
    if (ev.key.toLowerCase() === 'h' && !ev.ctrlKey && !ev.altKey && !ev.metaKey) {
      const tag = (document.activeElement && document.activeElement.tagName || '').toLowerCase();
      const codeEl = document.getElementById('pdv-code');
      // Permite 'h' se nao esta digitando num campo de texto E nao esta no campo codigo com algo digitado
      if (tag !== 'input' && tag !== 'textarea' || (document.activeElement === codeEl && !codeEl.value)) {
        ev.preventDefault();
        openPreco();  // reusa modal de consulta de preco
        return;
      }
    }

    // Ctrl+letra (atalhos de notebook preservados)
    if (ev.ctrlKey && !ev.shiftKey && !ev.altKey && !ev.metaKey) {
      const k = ev.key.toLowerCase();
      if (k === 'b') { ev.preventDefault(); openBusca(); return; }
      if (k === 'q') { ev.preventDefault(); changeQtySelected(); return; }
      if (k === 'd') { ev.preventDefault(); removeSelected(); return; }
      if (k === 'x') {
        if (!anyModalOpen()) {
          ev.preventDefault(); openCancelModal(); return;
        }
      }
      if (k === 'i') { ev.preventDefault(); openPreco(); return; }
      // Ctrl+1..9 → favorito N (Fase 14)
      if (/^[1-9]$/.test(k)) {
        const idx = parseInt(k, 10) - 1;
        const favs = allProducts.filter(p => p.favorite && p.active);
        if (idx < favs.length) {
          ev.preventDefault();
          addFavorite(favs[idx]);
        }
        return;
      }
    }
    // Fase 20: Setinhas sempre navegam.
    if (ev.key === 'ArrowUp' || ev.key === 'ArrowDown') {
      // Se tem modal aberto, deixa o navegador cuidar (foco em elementos do modal)
      if (anyModalOpen()) {
        // mas se o modal tem lista com data-nav="menu", navega pelos itens
        const list = document.querySelector('.modal:not([hidden]) [data-nav="menu"]');
        if (list) {
          ev.preventDefault();
          navigateMenu(list, ev.key === 'ArrowDown' ? 1 : -1);
          return;
        }
        return;
      }
      // Sem modal: navega itens do cupom
      if (!currentSale || !currentSale.items.length) return;
      const codeEl = document.getElementById('pdv-code');
      if (document.activeElement === codeEl && codeEl.value) return;
      ev.preventDefault();
      const n = currentSale.items.length;
      if (selectedIndex < 0) selectedIndex = 0;
      else selectedIndex = ev.key === 'ArrowUp'
        ? (selectedIndex - 1 + n) % n
        : (selectedIndex + 1) % n;
      renderSale();
      return;
    }
  }

  // Fase 20: navegacao com setinhas em listas de modais (menu de funcoes etc)
  function navigateMenu(container, direction) {
    const items = Array.from(container.querySelectorAll('[data-menu-item]'));
    if (!items.length) return;
    const current = container.querySelector('[data-menu-item].selected');
    let idx = current ? items.indexOf(current) : -1;
    idx = (idx + direction + items.length) % items.length;
    items.forEach(x => x.classList.remove('selected'));
    items[idx].classList.add('selected');
    items[idx].scrollIntoView({ block: 'nearest' });
  }

  function handleShortcutClick(ev) {
    const btn = ev.currentTarget;
    if (btn.classList.contains('disabled')) return;
    const action = btn.dataset.action;
    if (action === 'buscar') return openBusca();
    if (action === 'qty') return changeQtySelected();
    if (action === 'remover') return removeSelected();
    if (action === 'cancelar') return openCancelModal();
    if (action === 'preco') return openPreco();
    if (action === 'pagar') return openPagamento();
    if (action === 'reimprimir') return reprintLast();
    if (action === 'operacoes') {
      if (window.PdvOperacoes && window.PdvOperacoes.open) {
        window.PdvOperacoes.open();
      }
      return;
    }
  }

  document.addEventListener('DOMContentLoaded', () => {
    document.getElementById('pdv-code').addEventListener('keydown', handleCodeEnter);
    // Fase 18: btn-sair pode nao existir no PDV (header mudou pra operator selector).
    const btnSair = document.getElementById('btn-sair');
    if (btnSair) btnSair.addEventListener('click', doLogout);
    // Fase 20: atalhos numericos 1-5 pra escolher forma de pagamento no modal.
    document.addEventListener('keydown', handlePaymentModalKey);
    document.addEventListener('keydown', handleGlobalKey);

    // Botoes do rodape (notebook-friendly) + Fase 19 botoes ocultos
    document.querySelectorAll('.shortcut-btn, .shortcut-btn-hidden').forEach(btn => {
      btn.addEventListener('click', handleShortcutClick);
    });

    // Modais - botoes de fechar
    document.querySelectorAll('[data-close]').forEach(btn => {
      btn.addEventListener('click', () => closeAllModals());
    });
    document.getElementById('busca-input').addEventListener('input', debounce(doBusca, 250));
    document.getElementById('preco-input').addEventListener('keydown', ev => {
      if (ev.key === 'Enter') { ev.preventDefault(); doConsultaPreco(ev.currentTarget.value.trim()); }
    });

    // Modal pagamento
    document.getElementById('pay-discount-input').addEventListener('input', refreshPaymentCalc);
    document.getElementById('pay-discount-reason').addEventListener('input', () => {
      payState.discount_reason = document.getElementById('pay-discount-reason').value.trim();
    });
    document.getElementById('pay-add').addEventListener('click', () => {
      payState.payments.push({ method: 'dinheiro', amountStr: '0,00' });
      renderPaymentList();
      refreshPaymentCalc();
    });
    document.getElementById('pay-print').addEventListener('click', () => doFinalize(true));
    document.getElementById('pay-no-print').addEventListener('click', () => doFinalize(false));

    // devolve foco ao campo ao clicar fora
    document.addEventListener('click', (ev) => {
      const codeEl = document.getElementById('pdv-code');
      const insideModal = ev.target.closest('.modal:not([hidden])');
      const insideFav = ev.target.closest('.fav-btn, .pdv-items');
      if (!insideModal && !insideFav && document.activeElement !== codeEl) {
        setTimeout(() => codeEl.focus(), 10);
      }
    });

    loadProducts();
    loadOpenSale();
  });

  function debounce(fn, delay) {
    let t;
    return function () { clearTimeout(t); t = setTimeout(() => fn.apply(null, arguments), delay); };
  }
})();
