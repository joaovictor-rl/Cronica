// Componentes repetidos em várias páginas: lista de artigos, grade de pessoas, convites por código e foto.
import { api, postJson, send } from "./api.js";
import { esc } from "./render.js";
import { app, avatar, busy, count, formatDate, me, showError, thumb } from "./ui.js";

// ---------- início: lista de artigos ----------
const ROLE_LABEL = { dono: "Dono", coautor: "Coautor", membro: "Membro" };

const ROLE_TAG = { coautor: "coautor", organizacao: "pelo grupo" };

export function articleRows(articles, { showOrg = true } = {}) {
  return `<ul class="article-list">${articles.map((a) => `
    <li><a href="#/artigo/${a.id}">
      ${thumb(a.title)}
      <span><strong>${ROLE_TAG[a.role] ? `<span class="role-tag">${ROLE_TAG[a.role]}</span>` : ""}${esc(a.title)}</strong>
      <span class="muted">${a.versions ? `${count(a.versions, "versão", "versões")} · atualizado em ${formatDate(a.updated_at)}` : "nenhuma versão ainda"}</span>
      ${showOrg && a.org_name ? `<span class="org-line">em ${esc(a.org_name)}</span>` : ""}</span>
    </a></li>`).join("")}</ul>`;
}

export function inviteText(invite) {
  return invite.kind === "artigo"
    ? `convidou você para escrever o artigo <b>${esc(invite.target_name)}</b>`
    : `convidou você para entrar na organização <b>${esc(invite.target_name)}</b>`;
}

export function orgOptions(orgs, selected = null) {
  return `<option value="">Só meu (posso convidar coautores depois)</option>${orgs.map((o) =>
    `<option value="${o.id}" ${o.id === selected ? "selected" : ""}>Na organização ${esc(o.name)}</option>`).join("")}`;
}

export function personLink(person) {
  return person.id === me.id ? "#/perfil" : `#/pessoa/${person.id}`;
}

// Grade de pessoas no estilo "amigos" das redes antigas.
export function peopleGrid(members, { removable = () => false, wide = false } = {}) {
  return `<ul class="people-grid ${wide ? "wide" : ""}">${members.map((m) => `
    <li>
      <a href="${personLink(m.user)}" class="avatar-link">${avatar(m.user)}</a>
      <a href="${personLink(m.user)}" class="who">${esc(m.user.name)}${m.user.id === me.id ? " (você)" : ""}</a>
      <span class="role">${ROLE_LABEL[m.role] || m.role}</span>
      ${removable(m) ? `<button class="remove" data-remove="${m.user.id}" title="Tirar ${esc(m.user.name)}" aria-label="Tirar ${esc(m.user.name)}">×</button>` : ""}
    </li>`).join("")}</ul>`;
}

export function inviteForm(pending, what) {
  return `
    <form class="invite-form" id="invite-form">
      <label>Convidar pelo código pessoal
        <div class="row"><input name="code" required minlength="4" maxlength="20" placeholder="K7QM-4XPA" autocomplete="off" spellcheck="false">
        <button class="button small" type="submit">procurar</button></div>
      </label>
      <div id="invite-found" hidden></div>
      <p class="error" id="invite-error" hidden></p>
      <p class="muted">A pessoa encontra o código dela no próprio perfil, com o botão de copiar.</p>
    </form>
    ${pending.length ? `<p class="muted" style="margin:10px 0 0">esperando resposta:</p><ul class="pending-list">${pending.map((i) => `
      <li><span>${esc(i.receiver.name)}</span><button class="link-button" data-cancel="${i.id}" title="Cancelar o convite para ${what}">cancelar</button></li>`).join("")}</ul>` : ""}`;
}

// Procura o código, mostra quem é e só então envia o convite: assim ninguém convida a pessoa errada.
export function bindInvite({ invitePath, cancelPath, removePath, onChange }) {
  const form = document.getElementById("invite-form");
  if (form) {
    const found = document.getElementById("invite-found");
    const errorBox = document.getElementById("invite-error");
    form.onsubmit = async (event) => {
      event.preventDefault();
      errorBox.hidden = true;
      found.hidden = true;
      const code = new FormData(form).get("code").trim();
      try {
        const person = await api(`/users/by-code/${encodeURIComponent(code)}`);
        found.innerHTML = `<div class="found-person">${avatar(person)}<span><b>${esc(person.name)}</b>${person.institution ? `<br><span class="muted">${esc(person.institution)}</span>` : ""}</span>
          <button type="button" class="button small primary" id="invite-send">Convidar</button></div>`;
        found.hidden = false;
        document.getElementById("invite-send").onclick = async (e) => {
          const done = busy(e.target, "Enviando…");
          try {
            await postJson(invitePath, { code });
            onChange();
          } catch (error) {
            done();
            showError(errorBox, error);
          }
        };
      } catch (error) {
        showError(errorBox, error);
      }
    };
  }
  app.querySelectorAll("[data-cancel]").forEach((b) => {
    b.onclick = () => send(`${cancelPath}/${b.dataset.cancel}`, "DELETE").then(onChange);
  });
  app.querySelectorAll("[data-remove]").forEach((b) => {
    b.onclick = () => {
      if (confirm(`Tirar ${b.getAttribute("aria-label").replace(/^Tirar /, "")}?`)) {
        send(`${removePath}/${b.dataset.remove}`, "DELETE").then(onChange);
      }
    };
  });
}

export function photoField(item, render, uploadPath) {
  return `<div class="photo-field" id="photo-field">
    ${render(item)}
    <div class="buttons">
      <span class="button small file-button">Escolher foto<input type="file" accept="image/*" id="photo-input" aria-label="Escolher foto"></span>
      ${item.picture_at && uploadPath === "/auth/me/picture" ? `<button type="button" class="link-button" id="photo-remove">tirar a foto</button>` : ""}
      <span class="muted">JPG, PNG ou WebP, até 5 MB. A foto é recortada em quadrado.</span>
      <p class="error" id="photo-error" hidden></p>
    </div>
  </div>`;
}

export function bindPhoto(uploadPath, onDone) {
  const input = document.getElementById("photo-input");
  input.onchange = async () => {
    if (!input.files.length) return;
    const body = new FormData();
    body.append("file", input.files[0]);
    const label = input.parentElement;
    label.firstChild.textContent = "Enviando…";
    try {
      onDone(await api(uploadPath, { method: "POST", body }));
    } catch (error) {
      label.firstChild.textContent = "Escolher foto";
      showError(document.getElementById("photo-error"), error);
    }
  };
  const remove = document.getElementById("photo-remove");
  if (remove) remove.onclick = async () => onDone(await api(uploadPath, { method: "DELETE" }));
}
