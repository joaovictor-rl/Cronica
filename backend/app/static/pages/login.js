// Tela de entrada: login, cadastro e demonstração.
import { api, postJson, setSession } from "../api.js";
import { app, box, busy, go, showError } from "../ui.js";

// ---------- sessão ----------
async function login(email, password) {
  const data = await api("/auth/login", { method: "POST", body: new URLSearchParams({ username: email, password }) });
  setSession(data.access_token);
  go("#/");
}

export function renderLogin(mode = "login") {
  const isLogin = mode === "login";
  app.innerHTML = `
    <div class="welcome">
      <section class="welcome-text">
        <img src="/logo.svg" alt="Crônica" class="welcome-logo">
        <p class="tagline">seus artigos, versão por versão</p>
        <p>O <b>Crônica</b> guarda a história do seu artigo científico. Cada vez que você salva, fica uma versão, e dá para ver frase por frase o que mudou.</p>
        <ul class="features">
          <li><b>Escreva no site</b>, sem precisar saber LaTeX.</li>
          <li><b>Compare versões</b> e veja cada palavra trocada.</li>
          <li><b>Baixe o PDF</b> de qualquer versão.</li>
          <li><b>Usa o Overleaf?</b> Importe o projeto e leve de volta quando quiser.</li>
        </ul>
      </section>
      <div class="welcome-side">
        ${box(isLogin ? "Entre no Crônica" : "Crie sua conta", `
          <form id="auth-form" class="form">
            ${isLogin ? "" : `<label>Nome<input name="name" required autocomplete="name"></label>`}
            <label>E-mail<input name="email" type="email" required autocomplete="email"></label>
            <label>Senha<input name="password" type="password" required minlength="8" autocomplete="${isLogin ? "current-password" : "new-password"}"></label>
            ${isLogin ? "" : `<label class="check"><input type="checkbox" name="accept_privacy" required>
              <span>Li e concordo com a <a href="#/privacidade" target="_blank">política de privacidade</a>.</span></label>`}
            <p class="error" id="auth-error" hidden></p>
            <button class="button primary" type="submit">${isLogin ? "Entrar" : "Criar conta"}</button>
          </form>
          <p class="switch">${isLogin
            ? `Ainda não tem conta? <button class="link-button" data-mode="register">Crie uma agora</button>`
            : `Já tem conta? <button class="link-button" data-mode="login">Entrar</button>`}</p>
        `)}
        ${box("Só quer conhecer?", `
          <p>Abre uma cópia só sua de uma conta com um artigo real, escrito em grupo na UFPA, com quatro versões. Mexa à vontade: nada do que você fizer fica salvo nem aparece para outras pessoas.</p>
          <button class="button" id="demo-login">Entrar na demonstração</button>
        `)}
      </div>
    </div>
  `;
  app.querySelectorAll("[data-mode]").forEach((b) => { b.onclick = () => renderLogin(b.dataset.mode); });
  const errorBox = document.getElementById("auth-error");
  document.getElementById("auth-form").onsubmit = async (event) => {
    event.preventDefault();
    const data = Object.fromEntries(new FormData(event.target));
    try {
      if (!isLogin) await postJson("/auth/register", { ...data, accept_privacy: data.accept_privacy === "on" });
      await login(data.email, data.password);
    } catch (error) {
      showError(errorBox, error);
    }
  };
  document.getElementById("demo-login").onclick = async (event) => {
    const done = busy(event.target, "Preparando…");
    try {
      setSession((await postJson("/auth/demo", {})).access_token);
      go("#/");
    } catch (error) {
      done();
      showError(errorBox, error);
    }
  };
}
