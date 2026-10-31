/* Abrir operador: exigido antes de usar o PDV e o caixa. */
(function () {
  'use strict';

  const page = document.getElementById('operador-page');
  const list = document.getElementById('operadores-list');
  const erro = document.getElementById('erro-operador');
  const destino = page.dataset.next;

  function showErr(msg) {
    erro.textContent = msg;
    erro.hidden = false;
  }

  function botoes() {
    return Array.from(list.querySelectorAll('.admin-btn'));
  }

  async function abrir(id, btn) {
    btn.disabled = true;
    erro.hidden = true;
    try {
      const r = await fetch('/api/pdv/select-operator', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ operator_id: id }),
      });
      if (!r.ok) {
        showErr('Nao foi possivel abrir o operador. Tente novamente.');
        btn.disabled = false;
        btn.focus();
        return;
      }
      window.location.assign(destino);
    } catch (_) {
      showErr('Sistema fora do ar. Clique no icone PDV da area de trabalho.');
      btn.disabled = false;
      btn.focus();
    }
  }

  function render(operadores) {
    list.removeAttribute('aria-busy');
    while (list.firstChild) list.removeChild(list.firstChild);
    if (!operadores.length) {
      const p = document.createElement('p');
      p.className = 'admins-empty';
      p.textContent = 'Nenhum operador cadastrado. Cadastre no Painel do dono.';
      list.appendChild(p);
      return;
    }
    operadores.forEach(op => {
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'admin-btn';
      const nome = document.createElement('span');
      nome.className = 'admin-btn-name';
      nome.textContent = op.name;
      btn.appendChild(nome);
      btn.addEventListener('click', () => abrir(op.id, btn));
      list.appendChild(btn);
    });
    botoes()[0].focus();
  }

  document.addEventListener('keydown', ev => {
    if (ev.key !== 'ArrowUp' && ev.key !== 'ArrowDown') return;
    const itens = botoes();
    if (!itens.length) return;
    ev.preventDefault();
    const atual = itens.indexOf(document.activeElement);
    const passo = ev.key === 'ArrowDown' ? 1 : -1;
    itens[(atual + passo + itens.length) % itens.length].focus();
  });

  fetch('/api/pdv/operators')
    .then(r => r.json())
    .then(render)
    .catch(() => showErr('Falha ao carregar os operadores.'));
})();
