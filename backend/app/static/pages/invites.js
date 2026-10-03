// Convites recebidos: aceitar ou recusar.
import { send } from "../api.js";
import { esc } from "../render.js";
import { app, avatar, box, busy, codeLine, formatDate, go, invites, layout, me, profileCard, reload, showError } from "../ui.js";
import { inviteText, personLink } from "../widgets.js";

// ---------- convites ----------
export async function renderInvites() {
  layout(profileCard("convites"), `
    <section class="box">
      <header class="box-head big"><h1>Convites <span class="count">(${invites.length})</span></h1></header>
      <div class="box-body">
        <p class="error" id="invite-error" hidden></p>
        ${invites.length ? `<ul class="invite-list">${invites.map((i) => `
          <li>
            <a href="${personLink(i.sender)}">${avatar(i.sender)}</a>
            <div class="text"><a href="${personLink(i.sender)}"><b>${esc(i.sender.name)}</b></a> ${inviteText(i)}.
              <br><span class="muted">${i.sender.institution ? `${esc(i.sender.institution)} · ` : ""}${formatDate(i.created_at)}</span></div>
            <div class="buttons">
              <button class="button small primary" data-accept="${i.id}">Aceitar</button>
              <button class="button small" data-decline="${i.id}">Recusar</button>
            </div>
          </li>`).join("")}</ul>`
        : `<p class="muted empty-line">Nenhum convite esperando resposta.</p>`}
      </div>
    </section>
    ${box("Como alguém convida você", `
      <p>Passe o seu código pessoal para quem vai convidar. A pessoa cola o código no artigo ou na organização e o convite aparece aqui.</p>
      <p>${codeLine(me.code)}</p>
    `)}
  `);
  const errorBox = document.getElementById("invite-error");
  const answer = (id, action) => async (event) => {
    const done = busy(event.target, action === "accept" ? "Entrando…" : "Recusando…");
    const invite = invites.find((i) => i.id === id);
    try {
      await send(`/invites/${id}/${action}`);
      if (action === "decline") return reload();
      go(invite.kind === "artigo" ? `#/artigo/${invite.target_id}` : `#/organizacao/${invite.target_id}`);
    } catch (error) {
      done();
      showError(errorBox, error);
    }
  };
  app.querySelectorAll("[data-accept]").forEach((b) => { b.onclick = answer(Number(b.dataset.accept), "accept"); });
  app.querySelectorAll("[data-decline]").forEach((b) => { b.onclick = answer(Number(b.dataset.decline), "decline"); });
}
