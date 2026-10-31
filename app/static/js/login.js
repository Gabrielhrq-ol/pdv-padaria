(function () {
  const list = document.getElementById('admins-list');
  const err  = document.getElementById('erro-login');

  function showErr(msg) {
    err.textContent = msg;
    err.hidden = false;
  }

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, c => ({
      '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'
    }[c]));
  }

  function render(admins) {
    list.removeAttribute('aria-busy');
    if (!Array.isArray(admins) || !admins.length) {
      list.innerHTML = '<p class="admins-empty">Nenhum admin cadastrado ainda.</p>';
      return;
    }
    list.innerHTML = admins.map(a =>
      '<button type="button" class="admin-btn" data-id="' + a.id + '">' +
        '<span class="admin-btn-name">' + escapeHtml(a.nome) + '</span>' +
        '<span class="admin-btn-arrow">&rarr;</span>' +
      '</button>'
    ).join('');
    list.querySelectorAll('.admin-btn').forEach(btn => {
      btn.addEventListener('click', () => entrar(btn.dataset.id, btn));
    });
  }

  async function entrar(id, btn) {
    btn.disabled = true;
    btn.classList.add('loading');
    err.hidden = true;
    try {
      const r = await fetch('/auth/select-admin/' + id, { method: 'POST' });
      if (!r.ok) {
        showErr('Nao foi possivel entrar. Tente novamente.');
        btn.disabled = false;
        btn.classList.remove('loading');
        return;
      }
      window.location.href = '/admin';
    } catch (e) {
      showErr('Falha de rede. Tente novamente.');
      btn.disabled = false;
      btn.classList.remove('loading');
    }
  }

  fetch('/auth/admins')
    .then(r => r.json())
    .then(render)
    .catch(() => showErr('Falha carregando admins.'));
})();
