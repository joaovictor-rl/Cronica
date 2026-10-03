// Organizações: lista, página da organização (membros e artigos) e edição.
import { api, postJson, send, sendJson } from "../api.js";
import { esc } from "../render.js";
import { box, busy, count, formatDate, go, infoGrid, layout, me, notice, orgThumb, profileCard, reload, showError } from "../ui.js";
import { articleRows, bindInvite, bindPhoto, inviteForm, peopleGrid, photoField } from "../widgets.js";

// ---------- organizações ----------
export async function renderOrgs() {
  const orgs = await api("/orgs");
  layout(profileCard("organizacoes"), `
    <section class="box">
      <header class="box-head big">
        <h1>Organizações <span class="count">(${orgs.length})</span></h1>
        <button class="button" id="toggle-new">+ Nova organização</button>
      </header>
      <div class="box-body">
        ${notice("Para que serve", "Uma organização reúne um grupo de pesquisa, um laboratório ou uma turma. Todo mundo que entra nela lê e edita os artigos da organização, sem precisar convidar pessoa por pessoa em cada artigo.")}
        <form id="new-org" class="form" ${orgs.length ? "hidden" : ""}>
          <label>Nome<input name="name" required maxlength="120" placeholder="Ex.: Laboratório de IHC — UFPA"></label>
          <label>Descrição<textarea name="description" rows="3" maxlength="2000" placeholder="Quem participa, o que o grupo pesquisa."></textarea></label>
          <p class="error" id="org-error" hidden></p>
          <div><button class="button primary" type="submit">Criar organização</button></div>
        </form>
        ${orgs.length ? `<ul class="org-list">${orgs.map((o) => `
          <li><a href="#/organizacao/${o.id}">${orgThumb(o)}
            <span><strong>${esc(o.name)}</strong>
            <span class="muted">${count(o.members, "membro", "membros")} · ${count(o.articles, "artigo", "artigos")}${o.is_owner ? " · você criou" : ""}</span></span>
          </a></li>`).join("")}</ul>`
        : `<p class="muted empty-line">Você ainda não participa de nenhuma organização. Crie uma acima ou peça um convite.</p>`}
      </div>
    </section>
  `);
  const form = document.getElementById("new-org");
  document.getElementById("toggle-new").onclick = () => {
    form.hidden = false;
    form.querySelector("input").focus();
  };
  form.onsubmit = async (event) => {
    event.preventDefault();
    const done = busy(form.querySelector("[type=submit]"), "Criando…");
    try {
      const org = await postJson("/orgs", Object.fromEntries(new FormData(form)));
      go(`#/organizacao/${org.id}`);
    } catch (error) {
      done();
      showError(document.getElementById("org-error"), error);
    }
  };
}

function orgCard(org, active) {
  return `
    <section class="box profile-card">
      <div class="box-body">
        ${orgThumb(org, "big")}
        <a href="#/organizacao/${org.id}" class="profile-name">${esc(org.name)}</a>
        <p class="muted">${count(org.members, "membro", "membros")} · ${count(org.articles, "artigo", "artigos")}</p>
      </div>
    </section>
    <nav class="box side-menu" aria-label="Menu da organização">
      <a href="#/organizacao/${org.id}" class="${active === "pagina" ? "active" : ""}">Página da organização</a>
      ${org.is_owner ? `<a href="#/organizacao/${org.id}/editar" class="${active === "editar" ? "active" : ""}">Editar organização</a>`
        : `<button class="link-button" id="leave-org">Sair da organização</button>`}
      <a href="#/organizacoes">Todas as organizações</a>
    </nav>`;
}

export async function renderOrg(orgId) {
  const [org, people, articles] = await Promise.all([
    api(`/orgs/${orgId}`), api(`/orgs/${orgId}/members`), api(`/orgs/${orgId}/articles`),
  ]);
  layout(orgCard(org, "pagina"), `
    <section class="box">
      <header class="box-head big">
        <h1>${esc(org.name)}</h1>
        ${org.is_owner ? `<a href="#/organizacao/${org.id}/editar" class="button">✎ Editar</a>` : ""}
      </header>
      <div class="box-body">
        <p class="bio">${org.description ? esc(org.description) : `<span class="muted">Sem descrição.</span>`}</p>
        ${infoGrid([
          ["criada por", esc(org.owner.name)],
          ["criada em", formatDate(org.created_at, false)],
          ["membros", org.members],
          ["artigos", org.articles],
        ])}
      </div>
    </section>
    <section class="box">
      <header class="box-head"><h2>Artigos <span class="count">(${articles.length})</span></h2>
        <a class="button small" href="#/novo/${org.id}">+ Novo artigo aqui</a></header>
      <div class="box-body">
        ${articles.length ? articleRows(articles, { showOrg: false })
          : `<p class="muted">Nenhum artigo ainda. Crie um aqui, ou abra um artigo seu e escolha esta organização.</p>`}
      </div>
    </section>
  `, box(`Membros <span class="count">(${people.members.length})</span>`, `
      ${peopleGrid(people.members, { removable: (m) => org.is_owner && m.role !== "dono" })}
      ${org.is_owner ? inviteForm(people.pending, "a organização") : ""}
    `));

  bindInvite({
    invitePath: `/orgs/${orgId}/invites`, cancelPath: `/orgs/${orgId}/invites`,
    removePath: `/orgs/${orgId}/members`, onChange: reload,
  });
  const leave = document.getElementById("leave-org");
  if (leave) {
    leave.onclick = async () => {
      if (!confirm(`Sair de ${org.name}? Você deixa de ver os artigos da organização que não são seus.`)) return;
      await send(`/orgs/${orgId}/members/${me.id}`, "DELETE");
      go("#/organizacoes");
    };
  }
}

export async function renderOrgEdit(orgId) {
  let org = await api(`/orgs/${orgId}`);
  if (!org.is_owner) return go(`#/organizacao/${orgId}`);
  layout(orgCard(org, "editar"), `
    <section class="box">
      <header class="box-head big"><h1>Editar organização</h1></header>
      <div class="box-body">
        <form id="org-form" class="form profile-form">
          ${photoField(org, (o) => orgThumb(o), `/orgs/${orgId}/picture`)}
          <label>Nome<input name="name" required maxlength="120" value="${esc(org.name)}"></label>
          <label>Descrição<textarea name="description" rows="5" maxlength="2000">${esc(org.description)}</textarea></label>
          <p class="error" id="org-error" hidden></p>
          <div class="form-buttons"><a href="#/organizacao/${orgId}" class="button">Cancelar</a><button class="button primary" type="submit">Salvar</button></div>
        </form>
      </div>
    </section>
    ${box("Apagar organização", `
      <p>Os artigos não são apagados: voltam a ser só de quem os criou e dos coautores.</p>
      <button class="button" id="delete-org">Apagar ${esc(org.name)}</button>
    `)}
  `);
  const onPhoto = (updated) => {
    org = updated;
    document.querySelector(".profile-card .thumb").outerHTML = orgThumb(org, "big");
    document.getElementById("photo-field").outerHTML = photoField(org, (o) => orgThumb(o), `/orgs/${orgId}/picture`);
    bindPhoto(`/orgs/${orgId}/picture`, onPhoto);
  };
  bindPhoto(`/orgs/${orgId}/picture`, onPhoto);
  const form = document.getElementById("org-form");
  form.onsubmit = async (event) => {
    event.preventDefault();
    const data = new FormData(form);
    const done = busy(form.querySelector("[type=submit]"), "Salvando…");
    try {
      await sendJson(`/orgs/${orgId}`, { name: data.get("name"), description: data.get("description") }, "PATCH");
      go(`#/organizacao/${orgId}`);
    } catch (error) {
      done();
      showError(document.getElementById("org-error"), error);
    }
  };
  document.getElementById("delete-org").onclick = async () => {
    if (!confirm(`Apagar ${org.name}? Os membros deixam de ver os artigos da organização.`)) return;
    await send(`/orgs/${orgId}`, "DELETE");
    go("#/organizacoes");
  };
}
