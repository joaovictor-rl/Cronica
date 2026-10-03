// Ponto de entrada da interface: o topo do site e qual página mostrar para cada endereço (#/...).
import { api, hasSession, postJson, setSession, whenSessionExpires } from "./api.js";
import { esc } from "./render.js";
import { app, applyTheme, box, go, invites, logout, me, onNavigate, setInvites, setMe, setUnsaved, unsaved } from "./ui.js";
import { renderArticle } from "./pages/article.js";
import { renderEdit } from "./pages/edit.js";
import { renderHome, renderNewArticle } from "./pages/home.js";
import { renderInvites } from "./pages/invites.js";
import { renderLogin } from "./pages/login.js";
import { renderOrg, renderOrgEdit, renderOrgs } from "./pages/orgs.js";
import { renderPrivacy } from "./pages/privacy.js";
import { renderPerson, renderProfile } from "./pages/profile.js";

const nav = document.getElementById("nav");
const userArea = document.getElementById("user-area");

whenSessionExpires(() => {
  setMe(null);
  applyTheme(null);
  renderHeader();
  renderLogin();
});

function renderHeader(section) {
  document.body.classList.toggle("logged-out", !me);
  if (!me) {
    nav.innerHTML = "";
    userArea.innerHTML = "";
    renderDemoBar();
    return;
  }
  nav.innerHTML = `
    <a href="#/" class="${section === "inicio" ? "active" : ""}">Início</a>
    <a href="#/perfil" class="${section === "perfil" ? "active" : ""}">Perfil</a>
    <a href="#/organizacoes" class="${section === "organizacoes" ? "active" : ""}">Organizações</a>
    <a href="#/convites" class="${section === "convites" ? "active" : ""}">Convites${invites.length ? `<span class="badge-count" aria-label="${invites.length} esperando">${invites.length}</span>` : ""}</a>
  `;
  userArea.innerHTML = `<span>${me.is_demo ? "demonstração" : esc(me.email)}</span> | <button class="link-button" id="logout">sair</button>`;
  document.getElementById("logout").onclick = logout;
  renderDemoBar();
}

function renderDemoBar() {
  let bar = document.getElementById("demo-bar");
  if (!me || !me.is_demo) {
    if (bar) bar.remove();
    return;
  }
  if (!bar) {
    bar = Object.assign(document.createElement("div"), { id: "demo-bar", className: "demo-bar" });
    document.querySelector(".topbar").after(bar);
  }
  const ends = new Date(/[zZ]|[+-]\d\d:\d\d$/.test(me.expires_at) ? me.expires_at : me.expires_at + "Z");
  bar.innerHTML = `<div><span><b>Demonstração só sua.</b> Nada fica salvo: esta cópia some às
    ${ends.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" })} ou quando o site reiniciar.</span>
    <button class="link-button" id="demo-switch">Entrar como a outra conta da demonstração</button></div>`;
  document.getElementById("demo-switch").onclick = async () => {
    const data = await postJson("/auth/demo/switch", {});
    setSession(data.access_token);
    go("#/");
  };
}

// ---------- navegação ----------
async function route() {
  if (location.hash.startsWith("#/privacidade")) {
    renderHeader();
    renderPrivacy();
    return window.scrollTo(0, 0);
  }
  if (!hasSession()) {
    setMe(null);
    renderHeader();
    return renderLogin();
  }
  try {
    const [user, pending] = await Promise.all([api("/auth/me"), api("/invites")]);
    setMe(user);
    setInvites(pending);
    applyTheme(me.theme, me.pattern);
    const [page, id, second, third] = location.hash.replace(/^#\/?/, "").split("/");
    const sections = { perfil: "perfil", organizacoes: "organizacoes", organizacao: "organizacoes", convites: "convites" };
    renderHeader(sections[page] || "inicio");
    if (page === "perfil") await renderProfile(id === "editar");
    else if (page === "convites") await renderInvites();
    else if (page === "novo") await renderNewArticle(Number(id) || null);
    else if (page === "pessoa" && id) await renderPerson(Number(id));
    else if (page === "organizacoes") await renderOrgs();
    else if (page === "organizacao" && id) await (second === "editar" ? renderOrgEdit(Number(id)) : renderOrg(Number(id)));
    else if (page === "artigo" && id && (second === "editar" || second === "codigo")) await renderEdit(Number(id), second);
    else if (page === "artigo" && id) await renderArticle(Number(id), second, third);
    else await renderHome();
    window.scrollTo(0, 0);
  } catch (error) {
    if (!hasSession()) return;
    app.innerHTML = box("Algo deu errado", `<p>${esc(error.message)}</p><a href="#/" class="button">Voltar para o início</a>`);
  }
}

let previousHash = location.hash;

window.addEventListener("hashchange", () => {
  if (unsaved && !confirm("Você tem mudanças não salvas. Sair e perder essas mudanças?")) {
    history.replaceState(null, "", previousHash);
    return;
  }
  setUnsaved(false);
  previousHash = location.hash;
  route();
});

onNavigate(route);
route();
