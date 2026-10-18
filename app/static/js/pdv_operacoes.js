/*
  Modal "Operacoes do caixa" dentro do PDV (Fase 12).
  Reutiliza os endpoints /api/cash/*. Permite abrir, sangria, suprimento,
  fechar e consultar resumo sem sair da tela de venda.

  Exposto como window.PdvOperacoes.open() pra o pdv.js disparar via F12.
*/

(function () {
  'use strict';

  const API_CURRENT = '/api/cash/current';
  const API_SUMMARY = '/api/cash/current/summary';
  const API_OPEN = '/api/cash/open';
  const API_CLOSE = '/api/cash/close';
  const API_SANGRIA = '/api/cash/sangria';
  const API_SUPRIMENTO = '/api/cash/suprimento';

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
    const body = await resp.json().catch(() => ({}));
    if (!resp.ok && resp.status !== 404) {
      let msg = body.detail || resp.statusText || 'Erro.';
      const err = new Error(msg);
      err.status = resp.status;
      throw err;
    }
    if (resp.status === 404) {
      const err = new Error(body.detail || 'Nao encontrado');
      err.status = 404;
      throw err;
    }
    return body;
  }

  function formatBRL(cents) {
    const neg = cents < 0;
    const abs = Math.abs(cents | 0);
    const reais = Math.floor(abs / 100);
    const cs = (abs % 100).toString().padStart(2, '0');
    return (neg ? 'R$ -' : 'R$ ') + reais.toLocaleString('pt-BR') + ',' + cs;
  }

  function parseBRL(text) {
    if (text == null) throw new Error('Valor vazio.');
    let s = String(text).trim();
    if (!s) throw new Error('Valor vazio.');
    if (s.toUpperCase().startsWith('R$')) s = s.slice(2).trim();
    if (s.startsWith('-')) throw new Error('Valor negativo nao aceito.');
    const lastComma = s.lastIndexOf(',');
    const lastDot = s.lastIndexOf('.');
    let integerPart, decimalPart;
    if (lastComma === -1 && lastDot === -1) {
      integerPart = s;
      decimalPart = '';
    } else {
      const decimalSep = lastComma > lastDot ? ',' : '.';
      const thousandSep = decimalSep === ',' ? '.' : ',';
      const idx = s.lastIndexOf(decimalSep);
      integerPart = s.slice(0, idx).split(thousandSep).join('');
      decimalPart = s.slice(idx + 1);
    }
    if (integerPart === '') integerPart = '0';
    if (!/^\d+$/.test(integerPart)) throw new Error('Parte inteira invalida.');
    if (decimalPart && !/^\d+$/.test(decimalPart)) throw new Error('Parte decimal invalida.');
    if (decimalPart.length > 2) throw new Error('Mais de 2 casas decimais.');
    decimalPart = (decimalPart || '').padEnd(2, '0');
    return parseInt(integerPart, 10) * 100 + parseInt(decimalPart || '0', 10);
  }

  function clearNode(el) { while (el.firstChild) el.removeChild(el.firstChild); }

  function el(tag, attrs, children) {
    const node = document.createElement(tag);
    if (attrs) {
      for (const k in attrs) {
        if (k === 'className') node.className = attrs[k];
        else if (k === 'onclick') node.addEventListener('click', attrs[k]);
        else node.setAttribute(k, attrs[k]);
      }
    }
    (children || []).forEach(c => {
      if (c == null) return;
      if (typeof c === 'string') node.appendChild(document.createTextNode(c));
      else node.appendChild(c);
    });
    return node;
  }

  // ---------- modal control ----------

  function openModal() {
    const m = document.getElementById('modal-operacoes');
    m.hidden = false;
    render();
  }

  function closeModal() {
    const m = document.getElementById('modal-operacoes');
    m.hidden = true;
  }

  async function render() {
    const body = document.getElementById('ops-body');
    clearNode(body);
    body.appendChild(el('p', null, ['Carregando...']));

    let summary = null;
    try {
      summary = await apiFetch(API_SUMMARY);
    } catch (err) {
      if (err.status !== 404) {
        clearNode(body);
        body.appendChild(el('p', { className: 'erro-form' }, ['Erro: ' + err.message]));
        return;
      }
    }

    clearNode(body);
    if (!summary) {
      renderNoCash(body);
      return;
    }
    renderWithCash(body, summary);
  }

  // --- sem caixa aberto ---

  function renderNoCash(body) {
    body.appendChild(
      el('div', { className: 'ops-no-cash' }, [
        el('p', null, ['Nenhum caixa aberto.']),
        el('p', null, ['Abra o caixa pra comecar as vendas.']),
      ])
    );
    const form = el('form', { className: 'ops-form', id: 'ops-open-form' }, [
      el('div', { className: 'form-row' }, [
        el('label', { for: 'ops-open-cash' }, ['Fundo inicial (R$)']),
        el('input', {
          type: 'text', id: 'ops-open-cash', inputmode: 'decimal',
          placeholder: '0,00', value: '0,00',
        }),
      ]),
      el('div', { className: 'form-row' }, [
        el('label', { for: 'ops-open-notes' }, ['Observacao (opcional)']),
        el('input', {
          type: 'text', id: 'ops-open-notes', maxlength: '500',
          placeholder: 'turno manha, operador X',
        }),
      ]),
      el('div', { className: 'erro-form', id: 'ops-open-erro', hidden: 'hidden' }, []),
      el('div', { className: 'modal-actions' }, [
        el('button', { type: 'button', className: 'btn', onclick: closeModal }, ['Cancelar']),
        el('button', { type: 'submit', className: 'btn btn-primary' }, ['Abrir caixa']),
      ]),
    ]);
    body.appendChild(form);
    form.addEventListener('submit', submitOpen);
    const first = document.getElementById('ops-open-cash');
    if (first) first.focus();
  }

  async function submitOpen(ev) {
    ev.preventDefault();
    const erro = document.getElementById('ops-open-erro');
    erro.hidden = true; erro.textContent = '';
    let cents;
    try { cents = parseBRL(document.getElementById('ops-open-cash').value); }
    catch (e) { erro.textContent = e.message; erro.hidden = false; return; }
    const notes = document.getElementById('ops-open-notes').value.trim();
    const payload = { opening_cash_cents: cents };
    if (notes) payload.notes = notes;
    try {
      await apiFetch(API_OPEN, { method: 'POST', body: JSON.stringify(payload) });
      render();
    } catch (e) {
      erro.textContent = e.message; erro.hidden = false;
    }
  }

  // --- com caixa aberto ---

  function renderWithCash(body, s) {
    // bloco de status
    const session = s.session;
    const status = el('div', { className: 'ops-status' }, [
      el('div', null, [
        el('div', { className: 'ops-stat-label' }, ['Aberto por']),
        el('div', { className: 'ops-stat-value' }, [session.opened_by_name || '-']),
      ]),
      el('div', null, [
        el('div', { className: 'ops-stat-label' }, ['Fundo inicial']),
        el('div', { className: 'ops-stat-value' }, [formatBRL(session.opening_cash_cents)]),
      ]),
      el('div', null, [
        el('div', { className: 'ops-stat-label' }, ['Vendas (dinheiro)']),
        el('div', { className: 'ops-stat-value' }, [formatBRL(s.sales_cash_cents) + ' / ' + s.sales_count]),
      ]),
      el('div', null, [
        el('div', { className: 'ops-stat-label' }, ['Esperado em caixa']),
        el('div', { className: 'ops-stat-value' }, [formatBRL(s.expected_cash_cents)]),
      ]),
    ]);
    body.appendChild(status);

    // cards de acao
    const grid = el('div', { className: 'ops-grid' }, [
      el('div', {
        className: 'ops-card',
        onclick: () => showForm('sangria'),
      }, [
        el('strong', null, ['Sangria']),
        el('span', null, ['Retirar dinheiro']),
      ]),
      el('div', {
        className: 'ops-card success',
        onclick: () => showForm('suprimento'),
      }, [
        el('strong', null, ['Suprimento']),
        el('span', null, ['Colocar troco']),
      ]),
      el('div', {
        className: 'ops-card danger',
        onclick: () => showForm('fechar'),
      }, [
        el('strong', null, ['Fechar caixa']),
        el('span', null, ['Fim do dia']),
      ]),
      el('div', {
        className: 'ops-card',
        onclick: () => render(),
      }, [
        el('strong', null, ['Atualizar']),
        el('span', null, ['Recarregar resumo']),
      ]),
    ]);
    body.appendChild(grid);

    // Fase 19: cards de acoes da venda (F4/F8/F9/F10) tambem aqui.
    body.appendChild(el('h3', { style: 'margin-top:18px' }, ['Venda atual']));
    const grid2 = el('div', { className: 'ops-grid' }, [
      el('div', {
        className: 'ops-card',
        onclick: () => triggerVendaAction('remover'),
      }, [
        el('strong', null, ['Remover item (F4)']),
        el('span', null, ['Tira o item selecionado']),
      ]),
      el('div', {
        className: 'ops-card',
        onclick: () => triggerVendaAction('preco'),
      }, [
        el('strong', null, ['Consultar preço (F9)']),
        el('span', null, ['Sem adicionar à venda']),
      ]),
      el('div', {
        className: 'ops-card',
        onclick: () => triggerVendaAction('reimprimir'),
      }, [
        el('strong', null, ['Reimprimir (F10)']),
        el('span', null, ['2ª via da última venda']),
      ]),
      el('div', {
        className: 'ops-card danger',
        onclick: () => triggerVendaAction('cancelar'),
      }, [
        el('strong', null, ['Cancelar venda (F8)']),
        el('span', null, ['Com motivo obrigatório']),
      ]),
    ]);
    body.appendChild(grid2);
  }

  function triggerVendaAction(action) {
    closeModal();
    // Delega pro handler de atalhos do pdv.js (botao oculto com data-action)
    const btn = document.querySelector(`[data-action="${action}"]`);
    if (btn) btn.click();
  }

  // --- formularios inline (abrem no lugar dos cards) ---

  function showForm(kind) {
    const body = document.getElementById('ops-body');
    clearNode(body);
    if (kind === 'sangria') renderSangriaForm(body);
    else if (kind === 'suprimento') renderSuprimentoForm(body);
    else if (kind === 'fechar') renderFecharForm(body);
  }

  function renderSangriaForm(body) {
    body.appendChild(el('h3', null, ['Sangria']));
    const form = el('form', { className: 'ops-form' }, [
      el('div', { className: 'form-row' }, [
        el('label', null, ['Valor (R$) *']),
        el('input', { type: 'text', id: 'ops-sg-amount', inputmode: 'decimal', placeholder: '0,00' }),
      ]),
      el('div', { className: 'form-row' }, [
        el('label', null, ['Motivo (obrigatorio, min 3) *']),
        el('input', { type: 'text', id: 'ops-sg-reason', maxlength: '200', placeholder: 'ex: pagamento fornecedor' }),
      ]),
      el('div', { className: 'erro-form', id: 'ops-sg-erro', hidden: 'hidden' }, []),
      el('div', { className: 'modal-actions' }, [
        el('button', { type: 'button', className: 'btn', onclick: render }, ['Voltar']),
        el('button', { type: 'submit', className: 'btn btn-primary' }, ['Registrar sangria']),
      ]),
    ]);
    body.appendChild(form);
    form.addEventListener('submit', async (ev) => {
      ev.preventDefault();
      const erro = document.getElementById('ops-sg-erro');
      erro.hidden = true; erro.textContent = '';
      let cents;
      try { cents = parseBRL(document.getElementById('ops-sg-amount').value); }
      catch (e) { erro.textContent = e.message; erro.hidden = false; return; }
      const reason = document.getElementById('ops-sg-reason').value.trim();
      if (reason.length < 3) { erro.textContent = 'Motivo min 3 caracteres.'; erro.hidden = false; return; }
      try {
        await apiFetch(API_SANGRIA, {
          method: 'POST',
          body: JSON.stringify({ amount_cents: cents, reason: reason }),
        });
        render();
      } catch (e) { erro.textContent = e.message; erro.hidden = false; }
    });
    document.getElementById('ops-sg-amount').focus();
  }

  function renderSuprimentoForm(body) {
    body.appendChild(el('h3', null, ['Suprimento']));
    const form = el('form', { className: 'ops-form' }, [
      el('div', { className: 'form-row' }, [
        el('label', null, ['Valor (R$) *']),
        el('input', { type: 'text', id: 'ops-sp-amount', inputmode: 'decimal', placeholder: '0,00' }),
      ]),
      el('div', { className: 'form-row' }, [
        el('label', null, ['Motivo (opcional)']),
        el('input', { type: 'text', id: 'ops-sp-reason', maxlength: '200', placeholder: 'ex: reforco de troco' }),
      ]),
      el('div', { className: 'erro-form', id: 'ops-sp-erro', hidden: 'hidden' }, []),
      el('div', { className: 'modal-actions' }, [
        el('button', { type: 'button', className: 'btn', onclick: render }, ['Voltar']),
        el('button', { type: 'submit', className: 'btn btn-primary' }, ['Registrar suprimento']),
      ]),
    ]);
    body.appendChild(form);
    form.addEventListener('submit', async (ev) => {
      ev.preventDefault();
      const erro = document.getElementById('ops-sp-erro');
      erro.hidden = true; erro.textContent = '';
      let cents;
      try { cents = parseBRL(document.getElementById('ops-sp-amount').value); }
      catch (e) { erro.textContent = e.message; erro.hidden = false; return; }
      const reason = document.getElementById('ops-sp-reason').value.trim();
      const payload = { amount_cents: cents };
      if (reason) payload.reason = reason;
      try {
        await apiFetch(API_SUPRIMENTO, {
          method: 'POST', body: JSON.stringify(payload),
        });
        render();
      } catch (e) { erro.textContent = e.message; erro.hidden = false; }
    });
    document.getElementById('ops-sp-amount').focus();
  }

  async function renderFecharForm(body) {
    body.appendChild(el('h3', null, ['Fechar caixa']));
    let summary;
    try { summary = await apiFetch(API_SUMMARY); }
    catch (e) {
      body.appendChild(el('p', { className: 'erro-form' }, [e.message]));
      body.appendChild(el('div', { className: 'modal-actions' }, [
        el('button', { type: 'button', className: 'btn', onclick: render }, ['Voltar']),
      ]));
      return;
    }

    const expected = summary.expected_cash_cents;

    body.appendChild(el('div', { className: 'ops-status' }, [
      el('div', null, [
        el('div', { className: 'ops-stat-label' }, ['Esperado em caixa']),
        el('div', { className: 'ops-stat-value' }, [formatBRL(expected)]),
      ]),
    ]));

    const diffBox = el('div', { className: 'ops-stat-value', id: 'ops-fc-diff' }, ['—']);

    const form = el('form', { className: 'ops-form' }, [
      el('div', { className: 'form-row' }, [
        el('label', null, ['Dinheiro contado (R$) *']),
        el('input', { type: 'text', id: 'ops-fc-declared', inputmode: 'decimal', placeholder: '0,00' }),
      ]),
      el('div', { className: 'form-row' }, [
        el('label', null, ['Diferenca']),
        diffBox,
      ]),
      el('div', { className: 'form-row', id: 'ops-fc-reason-row', hidden: 'hidden' }, [
        el('label', null, ['Motivo da diferenca (min 3) *']),
        el('input', { type: 'text', id: 'ops-fc-reason', maxlength: '200' }),
      ]),
      el('div', { className: 'erro-form', id: 'ops-fc-erro', hidden: 'hidden' }, []),
      el('div', { className: 'modal-actions' }, [
        el('button', { type: 'button', className: 'btn', onclick: render }, ['Voltar']),
        el('button', { type: 'submit', className: 'btn btn-primary' }, ['Fechar caixa']),
      ]),
    ]);
    body.appendChild(form);

    const declaredInput = document.getElementById('ops-fc-declared');
    const reasonRow = document.getElementById('ops-fc-reason-row');

    declaredInput.addEventListener('input', () => {
      try {
        const declared = parseBRL(declaredInput.value);
        const diff = declared - expected;
        diffBox.textContent = (diff > 0 ? '+' : '') + formatBRL(diff);
        reasonRow.hidden = diff === 0;
      } catch (_) {
        diffBox.textContent = '—';
        reasonRow.hidden = true;
      }
    });

    form.addEventListener('submit', async (ev) => {
      ev.preventDefault();
      const erro = document.getElementById('ops-fc-erro');
      erro.hidden = true; erro.textContent = '';
      let declared;
      try { declared = parseBRL(declaredInput.value); }
      catch (e) { erro.textContent = e.message; erro.hidden = false; return; }
      const payload = { declared_cash_cents: declared };
      const diff = declared - expected;
      if (diff !== 0) {
        const reason = document.getElementById('ops-fc-reason').value.trim();
        if (reason.length < 3) {
          erro.textContent = 'Motivo min 3 caracteres (ha diferenca).';
          erro.hidden = false; return;
        }
        payload.difference_reason = reason;
      }
      try {
        await apiFetch(API_CLOSE, { method: 'POST', body: JSON.stringify(payload) });
        // Caixa fechado — se setting on, o backend vai redirecionar o PDV
        // na proxima tentativa de venda. Avisamos e fechamos.
        closeModal();
        if (window.showPdvToast) window.showPdvToast('Caixa fechado.', 'ok');
        // Reload do PDV pra pegar o novo estado (sem caixa aberto).
        setTimeout(() => window.location.reload(), 800);
      } catch (e) { erro.textContent = e.message; erro.hidden = false; }
    });
    declaredInput.focus();
  }

  // ---------- init ----------

  document.addEventListener('DOMContentLoaded', () => {
    // Fecha com Esc / botao X
    const modal = document.getElementById('modal-operacoes');
    if (!modal) return;
    modal.querySelectorAll('[data-close="modal-operacoes"]').forEach(b => {
      b.addEventListener('click', closeModal);
    });
    modal.addEventListener('click', (ev) => {
      if (ev.target === modal) closeModal();
    });
  });

  // API publica
  window.PdvOperacoes = {
    open: openModal,
    close: closeModal,
  };
})();
