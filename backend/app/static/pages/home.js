// Início (lista de artigos e importação do Overleaf) e criação de artigo a partir de um modelo.
import { api, postJson } from "../api.js";
import { esc } from "../render.js";
import { box, busy, count, go, invites, layout, notice, profileCard, showError } from "../ui.js";
import { articleRows, inviteText, orgOptions } from "../widgets.js";

export async function renderHome() {
  const articles = await api("/articles");
  layout(profileCard("artigos"), `
    ${invites.length ? notice(`Você tem ${count(invites.length, "convite", "convites")}`,
      `${esc(invites[0].sender.name)} ${inviteText(invites[0])}. <a href="#/convites">Ver ${invites.length > 1 ? "todos os convites" : "o convite"}</a>`) : ""}
    <section class="box">
      <header class="box-head big">
        <h1>Artigos <span class="count">(${articles.length})</span></h1>
        <a class="button primary" href="#/novo">+ Novo artigo</a>
      </header>
      <div class="box-body">
        <p class="error" id="article-error" hidden></p>
        ${articles.length ? articleRows(articles) : `
          <p class="muted empty-line">Você ainda não tem artigos. <a href="#/novo">Crie o primeiro</a> a partir de um modelo (SBC, ABNT, IEEE…): ele já vem com as seções e explica o que escrever em cada uma. Se alguém convidar você para um artigo, ele aparece aqui também.</p>`}
      </div>
    </section>
    ${box("Importar do Overleaf", `
      <form id="import" class="form">
        <p class="muted">Já tem o artigo no Overleaf? Abra <b>Menu → Download → Source</b> e escolha o arquivo .zip baixado.</p>
        <label>Arquivo .zip<input name="file" type="file" accept=".zip" required></label>
        <div><button class="button" type="submit">Importar artigo</button></div>
      </form>
    `)}
  `);

  const errorBox = document.getElementById("article-error");
  document.getElementById("import").onsubmit = async (event) => {
    event.preventDefault();
    const done = busy(event.target.querySelector("button"), "Importando…");
    try {
      const article = await api("/articles/import", { method: "POST", body: new FormData(event.target) });
      go(`#/artigo/${article.id}`);
    } catch (error) {
      done();
      showError(errorBox, error);
    }
  };
}

// ---------- novo artigo a partir de um modelo ----------
export async function renderNewArticle(orgId) {
  const [templates, orgs] = await Promise.all([api("/templates"), api("/orgs")]);
  const lang = { pt: "em português", en: "em inglês" };
  layout(profileCard("artigos"), `
    <form class="box" id="new-article">
      <header class="box-head big"><h1>Novo artigo</h1></header>
      <div class="box-body form">
        <label>Título<input name="title" required maxlength="300" placeholder="Ex.: Acessibilidade digital para idosos" autofocus></label>
        ${orgs.length ? `<label>Onde fica<select name="org_id">${orgOptions(orgs, orgId)}</select></label>` : ""}
        <fieldset class="template-picker">
          <legend>Escolha um modelo</legend>
          <p class="muted">O artigo já começa com as seções do modelo, e cada uma explica o que escrever nela. Dá para mudar tudo depois.</p>
          <div class="template-grid">${templates.map((t, i) => `
            <label class="template-card">
              <input type="radio" name="template" value="${t.id}" ${i === 0 ? "checked" : ""}>
              <span class="template-page"><img src="/templates/${t.id}/preview.png" alt="Primeira página do modelo ${esc(t.name)}" loading="lazy"></span>
              <span class="template-text">
                <strong>${esc(t.name)}</strong>
                <span class="template-use">${esc(t.use_for)}</span>
                <span class="muted">${esc(t.description)}</span>
                <span class="template-sections">${t.sections.map(esc).join(" · ")}</span>
                ${t.language !== "pt" ? `<span class="role-tag">${lang[t.language] || t.language}</span>` : ""}
              </span>
            </label>`).join("")}
          </div>
        </fieldset>
        ${notice("Sobre o PDF", "O PDF que o Crônica gera serve para ler e revisar. Para enviar a um evento no formato oficial do modelo, baixe o projeto (.zip) na página do artigo e abra no Overleaf: ele já vem com todos os arquivos do modelo.")}
        <p class="error" id="article-error" hidden></p>
        <div class="form-buttons"><a class="button" href="${orgId ? `#/organizacao/${orgId}` : "#/"}">Cancelar</a>
          <button class="button primary" type="submit">Criar e começar a escrever</button></div>
      </div>
    </form>
  `);
  const form = document.getElementById("new-article");
  form.onsubmit = async (event) => {
    event.preventDefault();
    const data = new FormData(form);
    const done = busy(form.querySelector("[type=submit]"), "Criando…");
    try {
      const article = await postJson("/articles", {
        title: data.get("title"), template: data.get("template"), org_id: Number(data.get("org_id")) || null,
      });
      go(`#/artigo/${article.id}/editar`);
    } catch (error) {
      done();
      showError(document.getElementById("article-error"), error);
    }
  };
}
