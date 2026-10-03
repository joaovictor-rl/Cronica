// Página do artigo: as páginas do PDF, o que mudou entre versões, histórico, pessoas e Overleaf.
import { api, blobUrl, download, send, sendJson } from "../api.js";
import { esc, fileDiffHtml } from "../render.js";
import { box, busy, count, formatDate, go, infoGrid, layout, me, notice, pdfPagesHtml, profileCard, reload, showError, showPdfPages, thumb } from "../ui.js";
import { bindInvite, inviteForm, orgOptions, peopleGrid } from "../widgets.js";

// ---------- página do artigo ----------
export async function renderArticle(articleId, selected, tab) {
  const [article, versions, people] = await Promise.all([
    api(`/articles/${articleId}`), api(`/articles/${articleId}/versions`), api(`/articles/${articleId}/members`),
  ]);
  const isOwner = article.role === "dono";
  const orgs = isOwner ? await api("/orgs") : [];
  if (!versions.length) {
    layout(profileCard("artigos"), box(esc(article.title), `<p class="muted">Este artigo ainda não tem versões.</p>`));
    return;
  }
  const current = versions.find((v) => v.hash === selected) || versions[0];
  const isLatest = current.hash === versions[0].hash;
  const number = (v) => versions.length - versions.indexOf(v);
  const hasPrevious = versions.indexOf(current) < versions.length - 1;
  tab = tab === "mudancas" && hasPrevious ? "mudancas" : "texto";
  const base = `#/artigo/${articleId}/${current.hash}`;

  const left = `
    <section class="box profile-card">
      <div class="box-body">
        ${thumb(article.title, "big")}
        <span class="profile-name">${esc(article.title)}</span>
        <p class="muted">${count(versions.length, "versão", "versões")}</p>
        ${article.org_name ? `<p class="org-line">em <a href="#/organizacao/${article.org_id}">${esc(article.org_name)}</a></p>` : ""}
      </div>
    </section>
    <nav class="box side-menu" aria-label="Menu do artigo">
      <a href="${base}/texto" class="${tab === "texto" ? "active" : ""}">Artigo</a>
      ${hasPrevious ? `<a href="${base}/mudancas" class="${tab === "mudancas" ? "active" : ""}">O que mudou</a>` : ""}
      ${isLatest ? `<a href="#/artigo/${articleId}/editar">Editar artigo</a>` : ""}
      <button class="link-button" id="side-pdf">Baixar PDF</button>
      ${article.role === "coautor" ? `<button class="link-button" id="leave-article">Sair deste artigo</button>` : ""}
      <a href="#/">Voltar para os artigos</a>
    </nav>
    ${box(`Pessoas <span class="count">(${people.members.length})</span>`, `
      ${peopleGrid(people.members, { removable: (m) => isOwner && m.role === "coautor" })}
      ${isOwner ? inviteForm(people.pending, "este artigo") : ""}
      ${article.role === "organizacao" ? `<p class="muted" style="margin:10px 0 0">Você entra neste artigo por ser membro de <b>${esc(article.org_name)}</b>.</p>` : ""}
    `, { cls: "people" })}
    ${isOwner && orgs.length ? box("Organização", `
      <p class="muted" style="margin:0">Quem é membro da organização lê e edita o artigo.</p>
      <div class="inline-select"><select id="org-select" aria-label="Organização do artigo">${orgOptions(orgs, article.org_id)}</select>
      <button class="button small" id="org-save">mudar</button></div>
    `) : ""}
  `;

  const right = `
    ${box("Histórico", `<ol class="timeline">
      ${versions.map((v) => `
        <li class="${v.hash === current.hash ? "selected" : ""}">
          <a href="#/artigo/${articleId}/${v.hash}/${tab}">
            <span class="version-label">versão ${number(v)}${v === versions[0] ? " · atual" : ""}</span>
            <strong>${esc(v.message)}</strong>
            <span class="muted">${formatDate(v.created_at)} · ${esc(v.author.name)}</span>
          </a>
        </li>`).join("")}
    </ol>`)}
    ${box("Overleaf", `
      <p class="muted">Leve esta versão para o Overleaf ou traga de lá uma versão nova.</p>
      <button class="button small" id="download-zip">Baixar projeto (.zip)</button>
      <form id="upload" class="form">
        <label>Versão do Overleaf (.zip)<input name="file" type="file" accept=".zip" required></label>
        <label>O que mudou?<input name="message" required maxlength="2000" placeholder="Ex.: Ajustes feitos no Overleaf"></label>
        <button class="button small" type="submit">Enviar versão</button>
      </form>
      <p class="error" id="upload-error" hidden></p>
    `, { cls: "overleaf" })}
  `;

  layout(left, `
    <section class="box">
      <header class="box-head big">
        <h1>${esc(article.title)}</h1>
        <div class="actions">
          ${isLatest ? `<a class="button primary" href="#/artigo/${articleId}/editar">✎ Editar artigo</a>` : `<a class="button" href="#/artigo/${articleId}">Ir para a versão atual</a>`}
          <button class="button" id="download-pdf">⬇ Baixar PDF</button>
        </div>
      </header>
      <div class="box-body">
        ${isLatest ? "" : notice("Versão antiga", `Você está vendo a versão ${number(current)} de ${versions.length}. Para editar, abra a versão atual.`)}
        ${infoGrid([
          ["versão", `${number(current)} de ${versions.length}${isLatest ? " (atual)" : ""}`],
          ["salva em", formatDate(current.created_at)],
          ["o que mudou", esc(current.message)],
          ["por", esc(current.author.name)],
          ["código", `<code title="${current.hash}">${current.hash.slice(0, 8)}</code>`],
          ["criado em", formatDate(article.created_at, false)],
        ])}
        <nav class="view-tabs">
          <a href="${base}/texto" class="${tab === "texto" ? "active" : ""}">Artigo</a>
          ${hasPrevious ? `<a href="${base}/mudancas" class="${tab === "mudancas" ? "active" : ""}">O que mudou</a>` : `<span class="disabled" title="Esta é a primeira versão">O que mudou</span>`}
        </nav>
        <p class="error" id="content-error" hidden></p>
        <div id="content"><p class="muted">Carregando…</p></div>
      </div>
    </section>
  `, right);

  bindInvite({
    invitePath: `/articles/${articleId}/invites`, cancelPath: `/articles/${articleId}/invites`,
    removePath: `/articles/${articleId}/members`, onChange: reload,
  });
  const leaveButton = document.getElementById("leave-article");
  if (leaveButton) {
    leaveButton.onclick = async () => {
      if (!confirm("Sair deste artigo? As versões que você salvou continuam no histórico, mas você deixa de ver o artigo.")) return;
      await send(`/articles/${articleId}/members/${me.id}`, "DELETE");
      go("#/");
    };
  }
  const orgSave = document.getElementById("org-save");
  if (orgSave) {
    orgSave.onclick = async () => {
      const value = Number(document.getElementById("org-select").value) || null;
      await sendJson(`/articles/${articleId}`, { org_id: value }, "PATCH");
      reload();
    };
  }

  const contentError = document.getElementById("content-error");
  const downloadPdf = async (event) => {
    const done = busy(event.target, "Gerando PDF…");
    try {
      await download(`/articles/${articleId}/versions/${current.hash}/pdf`, "artigo.pdf");
    } catch (error) {
      showError(contentError, error);
    } finally {
      done();
    }
  };
  document.getElementById("download-pdf").onclick = downloadPdf;
  document.getElementById("side-pdf").onclick = downloadPdf;
  document.getElementById("download-zip").onclick = (event) => {
    const done = busy(event.target, "Preparando…");
    download(`/articles/${articleId}/versions/${current.hash}/zip`, "projeto.zip").catch((e) => showError(contentError, e)).finally(done);
  };
  document.getElementById("upload").onsubmit = async (event) => {
    event.preventDefault();
    const data = new FormData(event.target);
    data.append("base_version", versions[0].hash);
    const done = busy(event.target.querySelector("button"), "Enviando…");
    try {
      const version = await api(`/articles/${articleId}/branches/main/commits`, { method: "POST", body: data });
      go(`#/artigo/${articleId}/${version.hash}/mudancas`);
    } catch (error) {
      done();
      showError(document.getElementById("upload-error"), error);
    }
  };

  const content = document.getElementById("content");
  try {
    if (tab === "mudancas") {
      const previous = versions[versions.indexOf(current) + 1];
      const diff = await api(`/articles/${articleId}/diff?from=${previous.hash}&to=${current.hash}`);
      content.innerHTML = `
        <p class="compare-note">Comparando com a versão ${number(previous)}: <b>${esc(previous.message)}</b>
          <span class="legend"><del>removido</del> <ins>adicionado</ins></span></p>
        ${diff.files.length ? diff.files.map(fileDiffHtml).join("") : `<p class="muted">Nenhum arquivo mudou.</p>`}`;
    } else {
      const { pages } = await api(`/articles/${articleId}/versions/${current.hash}/pages`);
      content.innerHTML = pdfPagesHtml(pages);
      showPdfPages(content, (n) => blobUrl(`/articles/${articleId}/versions/${current.hash}/pages/${n}.png`));
    }
  } catch (error) {
    content.innerHTML = `<p class="muted">${esc(error.message)}</p>`;
  }
}
