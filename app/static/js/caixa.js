/*
  Caixa (Fase 7) - abertura, sangria, suprimento, fechamento.

  Regras:
  - Nunca innerHTML com dado do servidor.
  - CSRF via X-CSRF-Token em toda rota mutante.
  - Dinheiro em string "0,00" na UI; centavos (int) no backend.
*/

(function () {
  'use strict';

  const API_CURRENT = '/api/cash/current';
  const API_SUMMARY = '/api/cash/current/summary';
  const API_OPEN = '/api/cash/open';
  const API_CLOSE = '/api/cash/close';
  const API_SANGRIA = '/api/cash/sangria';
  const API_SUPRIMENTO = '/api/cash/suprimento';
  const API_CASH_REQ = '/api/admin/settings/cash-required';

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
    if (resp.status === 401) {
      window.location.assign('/operador?next=/caixa');
      throw new Error('Nao autenticado.');
    }
    const ct = resp.headers.get('content-type') || '';
    const body = ct.indexOf('application/json') >= 0
      ? await resp.json() : await resp.text();
    if (resp.status === 404) {
      const err = new Error((body && body.detail) || 'Nao encontrado.');
      err.status = 404;
      throw err;
    }
    if (!resp.ok) {
      let msg = (body && body.detail) || resp.statusText || 'Erro.';
      if (body && Array.isArray(body.errors)) {
        msg = msg + ' ' + body.errors.map(e => e.msg || '').join('; ');
      }
      throw new Error(msg);
    }
    return body;
  }

  function formatBRL(cents) {
    const neg = cents < 0;
    const abs = Math.abs(cents | 0);
    const reais = Math.floor(abs / 100);
    const cs = (abs % 100).toString().padStart(2, '0');
    const reaisStr = reais.toLocaleString('pt-BR');
    return (neg ? 'R$ -' : 'R$ ') + reaisStr + ',' + cs;
  }

  // Converte "1.234,56" | "1234,56" | "1234.56" | "1234" em cents (int)
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
    const cents = parseInt(integerPart, 10) * 100 + parseInt(decimalPart || '0', 10);
    return cents;
  }

  function clearNode(el) {
    while (el.firstChild) el.removeChild(el.firstChild);
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
    if (!el) return;
    clearNode(el);
    el.className = 'feedback';
    if (!msg) return;
    el.classList.add(kind === 'ok' ? 'ok' : 'erro');
    el.textContent = msg;
    setTimeout(() => {
      if (el.textContent === msg) {
        clearNode(el);
        el.className = 'feedback';
      }
    }, 4000);
  }

  function formatDate(iso) {
    if (!iso) return '';
    const d = new Date(/Z$|[+-]\d\d:\d\d$/.test(iso) ? iso : iso + 'Z');
    if (isNaN(d.getTime())) return iso;
    const dd = String(d.getDate()).padStart(2, '0');
    const mm = String(d.getMonth() + 1).padStart(2, '0');
    const yyyy = d.getFullYear();
    const hh = String(d.getHours()).padStart(2, '0');
    const mi = String(d.getMinutes()).padStart(2, '0');
    return dd + '/' + mm + '/' + yyyy + ' ' + hh + ':' + mi;
  }

  function cell(text) {
    const td = document.createElement('td');
    td.textContent = text == null ? '' : String(text);
    return td;
  }

  // ---------- state ----------

  let currentSession = null;
  let currentSummary = null;

  // ---------- loaders ----------

  async function loadInitial() {
    // Query ?msg=abra -> flash
    const params = new URLSearchParams(window.location.search);
    if (params.get('msg') === 'abra') {
      showFeedback('Abra o caixa antes de usar o PDV.', 'erro');
    }
    try {
      await loadSummary();
    } catch (err) {
      if (err.status === 404) {
        renderNoSession();
      } else {
        showFeedback('Erro: ' + err.message, 'erro');
      }
    }
    // Admin: carrega status do setting
    const toggle = document.getElementById('toggle-cash-required');
    if (toggle) {
      try {
        const r = await apiFetch(API_CASH_REQ);
        toggle.checked = !!r.enabled;
      } catch (_) { /* nao-admin ou erro leve */ }
    }
  }

  async function loadSummary() {
    const summary = await apiFetch(API_SUMMARY);
    currentSummary = summary;
    currentSession = summary.session;
    renderOpenSession(summary);
  }

  // ---------- render ----------

  function renderNoSession() {
    document.getElementById('panel-aberto').hidden = true;
    document.getElementById('panel-abrir').hidden = false;
    currentSession = null;
    currentSummary = null;
    // Vindo do PDV o foco e abrir o caixa: nada de configuracao na frente.
    const config = document.getElementById('card-config');
    if (config && new URLSearchParams(window.location.search).get('msg') === 'abra') {
      config.hidden = true;
    }
    const campo = document.getElementById('abrir-cash');
    campo.focus();
    campo.select();
  }

  function renderOpenSession(summary) {
    document.getElementById('panel-abrir').hidden = true;
    document.getElementById('panel-aberto').hidden = false;
    document.getElementById('panel-relatorio').hidden = true;
    const s = summary.session;
    document.getElementById('info-aberto-por').textContent = s.opened_by_name || '-';
    document.getElementById('info-aberto-em').textContent = formatDate(s.opened_at);
    document.getElementById('info-fundo').textContent = formatBRL(s.opening_cash_cents);
    document.getElementById('info-vendas-cash').textContent =
      formatBRL(summary.sales_cash_cents) + ' (' + summary.sales_count + ' vendas)';

    // somas de suprimento / sangria
    let totalSupri = 0;
    let totalSangria = 0;
    summary.movements.forEach(m => {
      if (m.type === 'suprimento') totalSupri += m.amount_cents;
      else if (m.type === 'sangria') totalSangria += m.amount_cents;
    });
    document.getElementById('info-suprimentos').textContent = formatBRL(totalSupri);
    document.getElementById('info-sangrias').textContent = formatBRL(totalSangria);
    document.getElementById('info-esperado').textContent =
      formatBRL(summary.expected_cash_cents);

    // movimentos
    const tbody = document.getElementById('tbody-movs');
    const vazio = document.getElementById('movs-vazio');
    clearNode(tbody);
    if (!summary.movements.length) {
      vazio.hidden = false;
    } else {
      vazio.hidden = true;
      summary.movements.forEach(m => {
        const tr = document.createElement('tr');
        tr.appendChild(cell(formatDate(m.created_at)));
        const tdType = document.createElement('td');
        const badge = document.createElement('span');
        badge.className = 'badge badge-' + (m.type === 'sangria' ? 'perda' : 'entrada');
        badge.textContent = m.type === 'sangria' ? 'Sangria' : 'Suprimento';
        tdType.appendChild(badge);
        tr.appendChild(tdType);
        const tdAmount = document.createElement('td');
        tdAmount.className = 'num';
        const sign = m.type === 'sangria' ? '-' : '+';
        tdAmount.textContent = sign + ' ' + formatBRL(m.amount_cents);
        tr.appendChild(tdAmount);
        tr.appendChild(cell(m.reason || ''));
        tr.appendChild(cell(m.user_name || ''));
        tbody.appendChild(tr);
      });
    }

    // pagamentos
    const tbodyPg = document.getElementById('tbody-pagamentos');
    const vazioPg = document.getElementById('pagamentos-vazio');
    clearNode(tbodyPg);
    if (!summary.payments_by_method.length) {
      vazioPg.hidden = false;
    } else {
      vazioPg.hidden = true;
      summary.payments_by_method.forEach(p => {
        const tr = document.createElement('tr');
        tr.appendChild(cell(p.method));
        const tdQ = document.createElement('td');
        tdQ.className = 'num';
        tdQ.textContent = String(p.count);
        tr.appendChild(tdQ);
        const tdT = document.createElement('td');
        tdT.className = 'num';
        tdT.textContent = formatBRL(p.total_cents);
        tr.appendChild(tdT);
        tbodyPg.appendChild(tr);
      });
    }

    document.getElementById('fechar-esperado').textContent =
      formatBRL(summary.expected_cash_cents);
    updateFecharDiff();
  }

  function updateFecharDiff() {
    if (!currentSummary) return;
    const text = document.getElementById('fechar-declarado').value;
    const target = document.getElementById('fechar-diferenca');
    try {
      const declared = parseBRL(text);
      const diff = declared - currentSummary.expected_cash_cents;
      if (diff === 0) {
        target.textContent = formatBRL(0);
        target.className = '';
      } else {
        target.textContent = (diff > 0 ? 'Sobra ' : 'Falta ') + formatBRL(Math.abs(diff));
        target.className = diff > 0 ? 'diff-sobra' : 'diff-falta';
      }
    } catch (_) {
      target.textContent = '—';
      target.className = '';
    }
  }

  let relatorioSessaoId = null;

  function statusImpressao(printed, erro) {
    return printed
      ? 'Relatório enviado para a impressora.'
      : 'Não imprimiu: ' + (erro || 'erro desconhecido') + '. O caixa está fechado.';
  }

  function mostrarRelatorio(result) {
    relatorioSessaoId = result.id;
    document.getElementById('relatorio-linhas').textContent = (result.report_lines || []).join('\n');
    document.getElementById('relatorio-status').textContent =
      statusImpressao(result.printed, result.print_error);
    document.getElementById('panel-relatorio').hidden = false;
    window.scrollTo(0, 0);
  }

  async function reimprimirRelatorio() {
    if (!relatorioSessaoId) return;
    try {
      const r = await apiFetch('/api/cash/' + relatorioSessaoId + '/report/print', { method: 'POST' });
      document.getElementById('relatorio-status').textContent =
        statusImpressao(r.printed, r.print_error);
    } catch (err) {
      document.getElementById('relatorio-status').textContent = 'Erro: ' + err.message;
    }
  }

  // ---------- actions ----------

  async function submitAbrir(ev) {
    ev.preventDefault();
    showError('abrir-erro', null);
    let opening_cash_cents;
    try { opening_cash_cents = parseBRL(document.getElementById('abrir-cash').value); }
    catch (err) { showError('abrir-erro', err.message); return; }
    const notes = document.getElementById('abrir-notes').value.trim();
    const payload = { opening_cash_cents };
    if (notes) payload.notes = notes;
    try {
      await apiFetch(API_OPEN, { method: 'POST', body: JSON.stringify(payload) });
      window.location.assign('/pdv');
    } catch (err) {
      showError('abrir-erro', err.message);
    }
  }

  async function submitSangria(ev) {
    ev.preventDefault();
    showError('sangria-erro', null);
    let amount;
    try { amount = parseBRL(document.getElementById('sangria-amount').value); }
    catch (err) { showError('sangria-erro', err.message); return; }
    const reason = document.getElementById('sangria-reason').value.trim();
    if (reason.length < 3) {
      showError('sangria-erro', 'Motivo obrigatorio (min 3 caracteres).');
      return;
    }
    try {
      await apiFetch(API_SANGRIA, {
        method: 'POST',
        body: JSON.stringify({ amount_cents: amount, reason: reason }),
      });
      showFeedback('Sangria registrada.', 'ok');
      document.getElementById('form-sangria').reset();
      await loadSummary();
    } catch (err) {
      showError('sangria-erro', err.message);
    }
  }

  async function submitSuprimento(ev) {
    ev.preventDefault();
    showError('supri-erro', null);
    let amount;
    try { amount = parseBRL(document.getElementById('supri-amount').value); }
    catch (err) { showError('supri-erro', err.message); return; }
    const reason = document.getElementById('supri-reason').value.trim();
    const payload = { amount_cents: amount };
    if (reason) payload.reason = reason;
    try {
      await apiFetch(API_SUPRIMENTO, {
        method: 'POST',
        body: JSON.stringify(payload),
      });
      showFeedback('Suprimento registrado.', 'ok');
      document.getElementById('form-suprimento').reset();
      await loadSummary();
    } catch (err) {
      showError('supri-erro', err.message);
    }
  }

  async function submitFechar(ev) {
    ev.preventDefault();
    showError('fechar-erro', null);
    let declared;
    try { declared = parseBRL(document.getElementById('fechar-declarado').value); }
    catch (err) { showError('fechar-erro', err.message); return; }
    try {
      const result = await apiFetch(API_CLOSE, {
        method: 'POST',
        body: JSON.stringify({ declared_cash_cents: declared }),
      });
      showFeedback('Caixa fechado.', 'ok');
      renderNoSession();
      mostrarRelatorio(result);
    } catch (err) {
      showError('fechar-erro', err.message);
    }
  }

  async function toggleCashRequired(ev) {
    const enabled = ev.target.checked;
    try {
      await apiFetch(API_CASH_REQ, {
        method: 'PUT',
        body: JSON.stringify({ enabled: enabled }),
      });
      showFeedback(
        enabled ? 'Setting ativado: PDV exige caixa aberto.' : 'Setting desativado.',
        'ok'
      );
    } catch (err) {
      ev.target.checked = !enabled;
      showFeedback('Erro: ' + err.message, 'erro');
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
    document.getElementById('form-abrir').addEventListener('submit', submitAbrir);
    document.getElementById('form-sangria').addEventListener('submit', submitSangria);
    document.getElementById('form-suprimento').addEventListener('submit', submitSuprimento);
    document.getElementById('form-fechar').addEventListener('submit', submitFechar);
    document.getElementById('fechar-declarado').addEventListener('input', updateFecharDiff);
    document.getElementById('btn-reimprimir-relatorio').addEventListener('click', reimprimirRelatorio);
    const toggle = document.getElementById('toggle-cash-required');
    if (toggle) toggle.addEventListener('change', toggleCashRequired);
    document.getElementById('btn-sair').addEventListener('click', doLogout);
    loadInitial();
  });
})();
