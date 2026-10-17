/*
  Form de login. Envia JSON para /auth/login. Em caso de sucesso,
  redireciona para "/" - o backend decide pra onde ir baseado no papel:
  admin -> /admin (painel), caixa -> /pdv.
*/

(function () {
  'use strict';

  function showError(msg) {
    const el = document.getElementById('erro-login');
    if (!msg) {
      el.hidden = true;
      el.textContent = '';
    } else {
      el.hidden = false;
      el.textContent = msg;
    }
  }

  async function submitLogin(ev) {
    ev.preventDefault();
    showError(null);
    const username = document.getElementById('field-username').value.trim();
    const password = document.getElementById('field-password').value;
    const btn = document.getElementById('btn-entrar');
    btn.disabled = true;

    try {
      const resp = await fetch('/auth/login', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Accept': 'application/json',
        },
        body: JSON.stringify({ username: username, password: password }),
      });
      const body = await resp.json().catch(function () { return null; });
      if (!resp.ok) {
        let msg = (body && body.detail) || 'Falha ao entrar.';
        if (body && Array.isArray(body.errors)) {
          msg = msg + '\n' + body.errors.map(function (e) { return e.msg; }).join('\n');
        }
        showError(msg);
        btn.disabled = false;
        return;
      }
      // Sucesso: cookie session + csrf_token ja setados; redireciona.
      // "/" decide no backend baseado no papel (admin -> /admin, caixa -> /pdv).
      window.location.assign('/');
    } catch (err) {
      showError('Erro de conexao: ' + err.message);
      btn.disabled = false;
    }
  }

  document.addEventListener('DOMContentLoaded', function () {
    const form = document.getElementById('form-login');
    if (form) form.addEventListener('submit', submitLogin);
  });
})();
