// Peças usadas por todas as páginas: estado da sessão, navegação, tema, caixas, avatares e páginas do PDF.
import { blobUrl, hasSession, setSession } from "./api.js";
import { esc } from "./render.js";

export const app = document.getElementById("app");

const COLORS = ["#d6297a", "#3b6fc4", "#2f8f6b", "#c46a1f", "#7a4fc4", "#1f8aa8", "#b8405e"];

export const THEMES = [
  ["azul", "azul", "#e4ebf8", "#93b1e0"],
  ["rosa", "rosa", "#fbe4ef", "#e88ab2"],
  ["verde", "verde", "#e2f1e6", "#7cc093"],
  ["lilas", "lilás", "#ece6f8", "#a58fd8"],
  ["laranja", "laranja", "#fbebd9", "#eba768"],
  ["noite", "noite", "#1c2233", "#3a4766"],
];

const COPY_ICON = `<svg viewBox="0 0 16 16" aria-hidden="true"><rect x="5" y="5" width="9" height="9" rx="1.5" fill="none" stroke="currentColor" stroke-width="1.5"/><path d="M3.5 10.5h-1V2.5a1 1 0 0 1 1-1h7v1" fill="none" stroke="currentColor" stroke-width="1.5"/></svg>`;

// Quem está logado, convites pendentes e se há mudanças não salvas: lidos por todas as páginas.
export let me = null;
export let invites = [];
export let unsaved = false;
export function setMe(value) { me = value; }
export function setInvites(value) { invites = value; }
export function setUnsaved(value) { unsaved = value; }

// ---------- tema, fotos e botão de copiar ----------
export function showLook(theme, pattern) {
  if (theme && theme !== "azul") document.body.dataset.theme = theme;
  else delete document.body.dataset.theme;
  if (pattern && pattern !== "nenhum") document.body.dataset.pattern = pattern;
  else delete document.body.dataset.pattern;
}

// Guarda a aparência no navegador só para não piscar azul ao abrir; quem manda é o perfil salvo no servidor.
export function applyTheme(theme, pattern = null) {
  showLook(theme, pattern);
  try {
    if (theme) localStorage.setItem("cronica_look", JSON.stringify([theme, pattern]));
    else localStorage.removeItem("cronica_look");
  } catch { /* sem armazenamento local */ }
}

try {
  if (hasSession()) showLook(...JSON.parse(localStorage.getItem("cronica_look") || "[]"));
} catch { /* idem */ }

// Fotos precisam do token, então são baixadas pela API e trocadas por um endereço local.
function loadPictures(root) {
  for (const img of root.querySelectorAll("img[data-picture]")) {
    const path = img.dataset.picture;
    img.removeAttribute("data-picture");
    blobUrl(path).then((url) => { img.src = url; }).catch(() => { img.removeAttribute("src"); });
  }
}

new MutationObserver(() => loadPictures(document.body)).observe(document.body, { childList: true, subtree: true });

async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text);
  } catch {
    const field = Object.assign(document.createElement("textarea"), { value: text });
    document.body.append(field);
    field.select();
    document.execCommand("copy");
    field.remove();
  }
}

document.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-copy]");
  if (!button) return;
  await copyText(button.dataset.copy);
  const label = button.querySelector("span");
  button.classList.add("done");
  if (label) label.textContent = "copiado!";
  setTimeout(() => {
    button.classList.remove("done");
    if (label) label.textContent = "copiar";
  }, 1600);
});

export function codeLine(code) {
  return `<span class="code-line"><code>${esc(code)}</code><button type="button" class="copy" data-copy="${esc(code)}" title="Copiar código" aria-label="Copiar o código ${esc(code)}">${COPY_ICON}<span>copiar</span></button></span>`;
}

window.addEventListener("beforeunload", (event) => {
  if (unsaved) event.preventDefault();
});

// ---------- pedaços reaproveitados ----------
export function formatDate(value, withTime = true) {
  if (!value) return "—";
  const iso = /[zZ]|[+-]\d\d:\d\d$/.test(value) ? value : value + "Z";
  const options = withTime
    ? { day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" }
    : { day: "2-digit", month: "2-digit", year: "numeric" };
  return new Date(iso).toLocaleString("pt-BR", options);
}

function colorFor(text) {
  let sum = 0;
  for (const char of text) sum = (sum * 31 + char.charCodeAt(0)) % 9973;
  return COLORS[sum % COLORS.length];
}

function initials(name) {
  const words = name.trim().split(/\s+/).filter((w) => w.length > 2 || w === w.toUpperCase());
  return ((words[0]?.[0] || "?") + (words.length > 1 ? words[words.length - 1][0] : "")).toUpperCase();
}

export function avatar(person, size = "") {
  if (person.picture_at) {
    return `<img class="avatar ${size}" alt="" data-picture="/users/${person.id}/picture?v=${encodeURIComponent(person.picture_at)}">`;
  }
  return `<div class="avatar ${size}" style="background:${colorFor(person.name)}" aria-hidden="true">${esc(initials(person.name))}</div>`;
}

export function orgThumb(org, size = "") {
  if (org.picture_at) {
    return `<img class="thumb ${size}" alt="" data-picture="/orgs/${org.id}/picture?v=${encodeURIComponent(org.picture_at)}">`;
  }
  return thumb(org.name, size);
}

export function thumb(title, size = "") {
  const letter = title.replace(/^[^A-Za-zÀ-ÿ0-9]+/, "")[0] || "?";
  return `<div class="thumb ${size}" style="background:${colorFor(title)}" aria-hidden="true">${esc(letter.toUpperCase())}</div>`;
}

export function box(title, body, { action = "", cls = "" } = {}) {
  return `<section class="box ${cls}">
    ${title ? `<header class="box-head"><h2>${title}</h2>${action}</header>` : ""}
    <div class="box-body">${body}</div>
  </section>`;
}

export function infoGrid(rows) {
  return `<dl class="info-grid">${rows.filter(([, value]) => value !== null && value !== undefined && value !== "")
    .map(([label, value]) => `<div><dt>${label}:</dt><dd>${value}</dd></div>`).join("")}</dl>`;
}

export function notice(title, text) {
  return `<div class="notice"><strong>${title}</strong><p>${text}</p></div>`;
}

export function count(n, one, many) {
  return `${n} ${n === 1 ? one : many}`;
}

export function profileCard(active) {
  return `
    <section class="box profile-card">
      <div class="box-body">
        ${avatar(me, "big")}
        <a href="#/perfil" class="profile-name">${esc(me.name)}</a>
        ${me.status ? `<p class="status-line">${esc(me.status)}</p>` : ""}
        ${me.institution ? `<p class="muted">${esc(me.institution)}</p>` : ""}
        <p class="muted">${count(me.articles, "artigo", "artigos")} · ${count(me.versions, "versão", "versões")}</p>
        <div title="Passe este código para alguém convidar você">${codeLine(me.code)}</div>
      </div>
    </section>
    <nav class="box side-menu" aria-label="Menu do perfil">
      <a href="#/perfil" class="${active === "perfil" ? "active" : ""}">Perfil</a>
      <a href="#/" class="${active === "artigos" ? "active" : ""}">Artigos</a>
      <a href="#/organizacoes" class="${active === "organizacoes" ? "active" : ""}">Organizações</a>
      <a href="#/convites" class="${active === "convites" ? "active" : ""}">Convites${invites.length ? ` (${invites.length})` : ""}</a>
      <a href="#/perfil/editar" class="${active === "editar" ? "active" : ""}">Editar perfil</a>
      <button class="link-button" data-logout>Sair</button>
    </nav>
  `;
}

export function layout(left, main, right = "") {
  app.innerHTML = `<div class="layout ${right ? "three" : ""}">
    <aside class="col-left">${left}</aside>
    <div class="col-main">${main}</div>
    ${right ? `<aside class="col-right">${right}</aside>` : ""}
  </div>`;
  app.querySelectorAll("[data-logout]").forEach((b) => { b.onclick = logout; });
}

export function showError(element, error) {
  element.textContent = error.message;
  element.hidden = false;
}

export function busy(button, text) {
  const original = button.textContent;
  button.disabled = true;
  button.textContent = text;
  return () => {
    button.disabled = false;
    button.textContent = original;
  };
}

export function loadImages(articleId, versionHash) {
  return async (root) => {
    for (const img of root.querySelectorAll("img[data-src]")) {
      const path = img.dataset.src;
      img.removeAttribute("data-src");
      blobUrl(`/articles/${articleId}/versions/${versionHash}/images/${encodeURI(path)}`)
        .then((url) => { img.src = url; })
        .catch(() => img.replaceWith(Object.assign(document.createElement("p"), { className: "muted", textContent: `Imagem não encontrada: ${path}` })));
    }
  };
}

// O app.js registra aqui a função que desenha a página do endereço atual.
let router = () => {};
export function onNavigate(fn) { router = fn; }
export function reload() { router(); }

export function go(hash) {
  if (location.hash === hash) router();
  else location.hash = hash;
}

export function logout() {
  setSession(null);
  applyTheme(null);
  me = null;
  go("#/");
}

// ---------- páginas do PDF ----------
// A leitura no site mostra as páginas do próprio PDF: o que se vê é exatamente o que se baixa.
export function pdfPagesHtml(count) {
  return `<p class="muted pages-note">${count === 1 ? "1 página" : `${count} páginas`}, como no PDF.</p>
    <div class="pdf-pages">${Array.from({ length: count }, (_, i) => `
      <figure class="pdf-page" data-page="${i + 1}"><img alt="Página ${i + 1} de ${count}"><figcaption>${i + 1}</figcaption></figure>`).join("")}</div>`;
}

export function showPdfPages(root, source) {
  // Cada página só é baixada quando chega perto da tela.
  const observer = new IntersectionObserver((seen) => {
    for (const item of seen) {
      if (!item.isIntersecting) continue;
      observer.unobserve(item.target);
      const img = item.target.querySelector("img");
      Promise.resolve(source(Number(item.target.dataset.page))).then((url) => { img.src = url; }).catch(() => {
        item.target.classList.add("failed");
      });
    }
  }, { rootMargin: "600px 0px" });
  root.querySelectorAll(".pdf-page").forEach((page) => observer.observe(page));
}
