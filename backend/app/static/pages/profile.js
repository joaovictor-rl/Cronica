// Perfil: o seu (ver e editar, com aparência) e o de quem escreve com você.
import { api, download, postJson, sendJson } from "../api.js";
import { esc } from "../render.js";
import { THEMES, avatar, box, busy, codeLine, count, formatDate, go, infoGrid, layout, logout, me, notice, orgThumb, profileCard, setMe, showError, showLook, thumb } from "../ui.js";
import { bindPhoto, photoField } from "../widgets.js";

// ---------- perfil ----------
const PATTERNS = [["nenhum", "liso"], ["bolinhas", "bolinhas"], ["listras", "listras"], ["xadrez", "xadrez"], ["confete", "confete"]];

function themePicker(current) {
  return `<fieldset class="theme-picker"><legend>Cor do fundo</legend>${THEMES.map(([value, label, bg, tab]) => `
    <label><input type="radio" name="theme" value="${value}" ${current === value ? "checked" : ""}>
      <span class="swatch"><i style="background:${tab}"></i><i style="background:${bg}"></i></span>${label}</label>`).join("")}
  </fieldset>`;
}

function patternPicker(current) {
  return `<fieldset class="theme-picker"><legend>Desenho do fundo</legend>${PATTERNS.map(([value, label]) => `
    <label><input type="radio" name="pattern" value="${value}" ${current === value ? "checked" : ""}>
      <span class="swatch pattern" data-pattern="${value}"></span>${label}</label>`).join("")}
  </fieldset>`;
}

const LINKS = [["lattes", "Lattes"], ["orcid", "ORCID"], ["website", "Site"]];

function linkList(person) {
  const items = LINKS.filter(([key]) => person[key]);
  if (!items.length) return "";
  return `<ul class="links">${items.map(([key, label]) => `
    <li><b>${label}</b> <a href="${esc(person[key])}" target="_blank" rel="noopener noreferrer nofollow">${esc(person[key].replace(/^https?:\/\//, ""))}</a></li>`).join("")}</ul>`;
}

function tagList(items) {
  return `<ul class="tags">${items.map((t) => `<li>${esc(t)}</li>`).join("")}</ul>`;
}

// Mostra o que a pessoa escreveu sobre si: frase, sobre mim, interesses e links.
function aboutSections(person, own) {
  const empty = (text) => own ? `<span class="muted">${text} <a href="#/perfil/editar">Preencher agora</a></span>` : `<span class="muted">${text}</span>`;
  return `
    <h3 class="section-title">Sobre mim</h3>
    <p class="bio">${person.bio ? esc(person.bio) : empty("Nada escrito ainda.")}</p>
    <h3 class="section-title">Interesses de pesquisa</h3>
    ${person.interests.length ? tagList(person.interests) : `<p>${empty("Nenhum interesse informado.")}</p>`}
    ${linkList(person) ? `<h3 class="section-title">Links</h3>${linkList(person)}` : ""}`;
}

export async function renderProfile(editing) {
  const [articles, orgs] = await Promise.all([api("/articles"), api("/orgs")]);
  const info = infoGrid([
    ["código pessoal", codeLine(me.code)],
    ["instituição", esc(me.institution) || `<span class="muted">não informada</span>`],
    ["área de pesquisa", esc(me.area) || `<span class="muted">não informada</span>`],
    ["cidade", esc(me.city) || `<span class="muted">não informada</span>`],
    ["e-mail", me.is_demo ? `<span class="muted">conta de demonstração</span>` : esc(me.email)],
    ["membro desde", formatDate(me.created_at, false)],
    ["última atividade", formatDate(me.last_activity)],
    ["artigos", me.articles],
    ["versões salvas", me.versions],
  ]);

  const form = `
    <form id="profile-form" class="form profile-form">
      <fieldset class="form-group"><legend>Aparência</legend>
        ${photoField(me, (m) => avatar(m), "/auth/me/picture")}
        ${themePicker(me.theme)}
        ${patternPicker(me.pattern)}
        <p class="muted" style="margin:0">Quem abre o seu perfil vê ele com estas cores.</p>
      </fieldset>
      <fieldset class="form-group"><legend>Sobre você</legend>
        <label>Nome<input name="name" required maxlength="120" value="${esc(me.name)}"></label>
        <label>Frase do perfil <span class="hint">(aparece embaixo do seu nome, até 140 letras)</span>
          <input name="status" maxlength="140" value="${esc(me.status)}" placeholder="Ex.: Escrevendo a dissertação ✍"></label>
        <div class="form-row">
          <label>Instituição<input name="institution" maxlength="200" value="${esc(me.institution)}" placeholder="Ex.: Universidade Federal do Pará (UFPA)"></label>
          <label>Área de pesquisa<input name="area" maxlength="200" value="${esc(me.area)}" placeholder="Ex.: Interação Humano-Computador"></label>
        </div>
        <label>Cidade<input name="city" maxlength="120" value="${esc(me.city)}" placeholder="Ex.: Belém, PA"></label>
        <label>Sobre mim<textarea name="bio" rows="4" maxlength="1000" placeholder="Conte em poucas linhas o que você pesquisa.">${esc(me.bio)}</textarea></label>
        <label>Interesses de pesquisa <span class="hint">(separe com vírgulas, até 10)</span>
          <input name="interests" value="${esc(me.interests.join(", "))}" placeholder="Ex.: Acessibilidade, Usabilidade, Saúde digital"></label>
      </fieldset>
      <fieldset class="form-group"><legend>Links</legend>
        <div class="form-row">
          <label>Currículo Lattes<input name="lattes" maxlength="300" value="${esc(me.lattes)}" placeholder="http://lattes.cnpq.br/…"></label>
          <label>ORCID<input name="orcid" maxlength="300" value="${esc(me.orcid)}" placeholder="0000-0000-0000-0000"></label>
        </div>
        <label>Site ou portfólio<input name="website" maxlength="300" value="${esc(me.website)}" placeholder="Ex.: github.com/seu-usuario"></label>
      </fieldset>
      <p class="error" id="profile-error" hidden></p>
      <div class="form-buttons"><a href="#/perfil" class="button">Cancelar</a><button class="button primary" type="submit">Salvar perfil</button></div>
    </form>`;

  layout(profileCard(editing ? "editar" : "perfil"), `
    <section class="box">
      <header class="box-head big">
        <div><h1>${editing ? "Editar perfil" : esc(me.name)}</h1>
        ${!editing && me.status ? `<p class="status-line">${esc(me.status)}</p>` : ""}</div>
        ${editing ? "" : `<a href="#/perfil/editar" class="button">✎ Editar perfil</a>`}
      </header>
      <div class="box-body">
        ${editing ? "" : notice("Quem vê o seu perfil", "Coautores, membros das suas organizações e quem trocou convites com você veem o perfil sem o e-mail e sem o código. Mais ninguém vê.")}
        ${editing ? form : `${info}${aboutSections(me, true)}`}
      </div>
    </section>
    ${editing ? "" : box(`Artigos <span class="count">(${articles.length})</span>`, articles.length
      ? `<div class="tile-grid">${articles.slice(0, 9).map((a) => `
          <a href="#/artigo/${a.id}" class="tile">${thumb(a.title, "medium")}<span>${esc(a.title)}</span><span class="muted">${count(a.versions, "versão", "versões")}</span></a>`).join("")}</div>`
      : `<p class="muted">Nenhum artigo ainda. <a href="#/">Criar o primeiro</a></p>`)}
    ${editing ? "" : box(`Organizações <span class="count">(${orgs.length})</span>`, orgs.length
      ? `<div class="tile-grid">${orgs.map((o) => `
          <a href="#/organizacao/${o.id}" class="tile">${orgThumb(o, "medium")}<span>${esc(o.name)}</span><span class="muted">${count(o.members, "membro", "membros")}</span></a>`).join("")}</div>`
      : `<p class="muted">Você ainda não participa de nenhuma organização. <a href="#/organizacoes">Criar uma</a></p>`)}
    ${editing ? "" : box("Seus dados", `
      <p>Você pode baixar tudo o que o Crônica guarda sobre você ou excluir a sua conta. <a href="#/privacidade">Como tratamos os seus dados</a></p>
      <p><button class="button" id="export-data">Baixar meus dados (.zip)</button></p>
      <form id="delete-account" class="form delete-account">
        <p class="muted">Excluir a conta apaga o seu perfil e os artigos que você criou, também para os coautores. Não dá para desfazer.</p>
        ${me.is_demo ? "" : `<label>Sua senha, para confirmar<input name="password" type="password" required autocomplete="current-password"></label>`}
        <p class="error" id="delete-error" hidden></p>
        <div><button class="button danger-button" type="submit">Excluir minha conta</button></div>
      </form>
    `)}
  `);

  if (!editing) {
    document.getElementById("export-data").onclick = (event) => {
      const done = busy(event.target, "Preparando…");
      download("/auth/me/export", "meus-dados-cronica.zip").finally(done);
    };
    const remove = document.getElementById("delete-account");
    remove.onsubmit = async (event) => {
      event.preventDefault();
      if (!confirm("Excluir a sua conta e os artigos que você criou? Não dá para desfazer.")) return;
      try {
        await postJson("/auth/me/delete", { password: remove.password?.value || "-" });
        logout();
      } catch (error) {
        showError(document.getElementById("delete-error"), error);
      }
    };
  }

  if (editing) {
    const formElement = document.getElementById("profile-form");
    // Cor e desenho mudam na hora, para a pessoa ver antes de salvar; "Cancelar" volta para o que estava salvo.
    const preview = () => {
      const data = new FormData(formElement);
      showLook(data.get("theme"), data.get("pattern"));
    };
    formElement.querySelectorAll("[name=theme], [name=pattern]").forEach((radio) => { radio.onchange = preview; });
    const onPhoto = (updated) => {
      setMe({ ...me, picture_at: updated.picture_at });
      document.querySelector(".profile-card .avatar").outerHTML = avatar(me, "big");
      const field = document.getElementById("photo-field");
      field.outerHTML = photoField(me, (m) => avatar(m), "/auth/me/picture");
      bindPhoto("/auth/me/picture", onPhoto);
    };
    bindPhoto("/auth/me/picture", onPhoto);
    formElement.onsubmit = async (event) => {
      event.preventDefault();
      const data = Object.fromEntries(new FormData(formElement));
      data.interests = data.interests.split(/[,;\n]/).map((t) => t.trim()).filter(Boolean);
      const done = busy(formElement.querySelector("[type=submit]"), "Salvando…");
      try {
        setMe(await sendJson("/auth/me", data, "PATCH"));
        go("#/perfil");
      } catch (error) {
        done();
        showError(document.getElementById("profile-error"), error);
      }
    };
  }
}

// ---------- perfil de outra pessoa ----------
export async function renderPerson(personId) {
  if (personId === me.id) return go("#/perfil");
  const person = await api(`/users/${personId}`);
  showLook(person.theme, person.pattern); // o perfil aparece com as cores que a pessoa escolheu
  layout(`
    <section class="box profile-card">
      <div class="box-body">
        ${avatar(person, "big")}
        <span class="profile-name">${esc(person.name)}</span>
        ${person.institution ? `<p class="muted">${esc(person.institution)}</p>` : ""}
        ${person.city ? `<p class="muted">${esc(person.city)}</p>` : ""}
      </div>
    </section>
    <nav class="box side-menu" aria-label="Menu">
      <a href="#/perfil">Meu perfil</a>
      <a href="#/">Artigos</a>
      <button class="link-button" id="back">Voltar</button>
    </nav>`, `
    <section class="box">
      <header class="box-head big"><div><h1>${esc(person.name)}</h1>
        ${person.status ? `<p class="status-line">${esc(person.status)}</p>` : ""}</div></header>
      <div class="box-body">
        ${infoGrid([
          ["instituição", esc(person.institution)],
          ["área de pesquisa", esc(person.area)],
          ["cidade", esc(person.city)],
          ["membro desde", formatDate(person.created_at, false)],
        ])}
        ${aboutSections(person, false)}
        <p class="visit-note">Você está vendo este perfil com as cores que ${esc(person.name.split(" ")[0])} escolheu.</p>
      </div>
    </section>
    ${box(`Artigos em comum <span class="count">(${person.shared_articles.length})</span>`, person.shared_articles.length
      ? `<div class="tile-grid">${person.shared_articles.map((a) => `
          <a href="#/artigo/${a.id}" class="tile">${thumb(a.title, "medium")}<span>${esc(a.title)}</span></a>`).join("")}</div>`
      : `<p class="muted">Nenhum artigo em comum ainda.</p>`)}
    ${person.shared_orgs.length ? box(`Organizações em comum <span class="count">(${person.shared_orgs.length})</span>`,
      `<div class="tile-grid">${person.shared_orgs.map((o) => `
          <a href="#/organizacao/${o.id}" class="tile">${orgThumb(o, "medium")}<span>${esc(o.name)}</span></a>`).join("")}</div>`) : ""}
  `);
  document.getElementById("back").onclick = () => history.back();
}
