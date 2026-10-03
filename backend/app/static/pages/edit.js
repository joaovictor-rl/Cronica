// Editor: o artigo editável, figuras, referências, prévia do PDF e salvar uma versão nova.
import { api, apiText, postJson } from "../api.js";
import { esc } from "../render.js";
import { Editor } from "../editor.js";
import { app, busy, go, loadImages, setUnsaved, showError, unsaved } from "../ui.js";

// ---------- edição ----------
// Campos do formulário de referência, por tipo de obra.
const REF_FIELDS = {
  article: [["journal", "Revista"], ["volume", "Volume"], ["number", "Número"], ["pages", "Páginas"]],
  inproceedings: [["booktitle", "Nome do evento (anais)"], ["pages", "Páginas"], ["address", "Cidade"], ["publisher", "Editora ou sociedade"]],
  book: [["publisher", "Editora"], ["address", "Cidade"], ["edition", "Edição"]],
  incollection: [["booktitle", "Título do livro"], ["editor", "Organizadores"], ["publisher", "Editora"], ["address", "Cidade"], ["pages", "Páginas"]],
  phdthesis: [["school", "Universidade"], ["address", "Cidade"]],
  mastersthesis: [["school", "Universidade"], ["address", "Cidade"]],
  techreport: [["institution", "Instituição"], ["number", "Número"], ["address", "Cidade"]],
  misc: [["howpublished", "Onde foi publicado (site, jornal...)"], ["urlaccessdate", "Acessado em"]],
};

function fileToBase64(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result).split(",")[1]);
    reader.onerror = () => reject(new Error("Não consegui ler a imagem."));
    reader.readAsDataURL(file);
  });
}

function imageName(file) {
  const base = file.name.replace(/\.[^.]+$/, "").normalize("NFKD").replace(/[̀-ͯ]/g, "")
    .toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 40) || "imagem";
  const ext = /jpe?g$/i.test(file.type) || /\.jpe?g$/i.test(file.name) ? "jpg" : "png";
  return `imagens/${base}-${Math.random().toString(36).slice(2, 6)}.${ext}`;
}

export async function renderEdit(articleId, mode) {
  const [article, versions] = await Promise.all([api(`/articles/${articleId}`), api(`/articles/${articleId}/versions`)]);
  const head = versions[0];
  const code = mode === "codigo";
  const refs = await api(`/articles/${articleId}/versions/${head.hash}/references`);
  let refsChanged = false;
  const newImages = new Map(); // caminho → { file, url }

  app.innerHTML = `
    <div class="edit-bar box">
      <div class="edit-title">
        <a href="#/artigo/${articleId}" class="back" id="cancel">← voltar sem salvar</a>
        <strong>${esc(article.title)}</strong>
        <span class="muted" id="status">Nenhuma mudança ainda</span>
      </div>
      <div class="edit-tools" ${code ? "hidden" : ""}>
        <button class="tool" data-format="bold" title="Negrito (Ctrl+B)"><b>N</b></button>
        <button class="tool" data-format="italic" title="Itálico (Ctrl+I)"><i>I</i></button>
        <span class="tool-sep"></span>
        <button class="tool" data-insert="paragraph">+ Parágrafo</button>
        <button class="tool" data-insert="section">+ Seção</button>
        <button class="tool" data-insert="subsection">+ Subseção</button>
        <button class="tool" data-insert="list">+ Lista</button>
        <label class="tool file-tool" title="Escolha uma imagem do computador (PNG ou JPG)">+ Figura<input type="file" accept="image/*" id="figure-input"></label>
        <span class="tool-sep"></span>
        <button class="tool" data-open-references title="Adicionar obras e citar no texto">❝ Referências <span id="ref-count">(${refs.entries.length})</span></button>
        <span class="tool-sep"></span>
        <button class="tool danger" id="remove-block">Remover bloco</button>
      </div>
      <div class="edit-actions">
        <a class="link-button" href="#/artigo/${articleId}/${code ? "editar" : "codigo"}" id="switch-mode">${code ? "editor visual" : "código LaTeX"}</a>
        <button class="button" id="preview-button" title="Mostra o PDF com as mudanças, antes de salvar">Ver como PDF</button>
        <button class="button primary" id="save" disabled>Salvar versão</button>
      </div>
    </div>
    <form class="save-panel box" id="save-panel" hidden>
      <div class="box-body">
        <label>O que você mudou nesta versão?
          <input name="message" required maxlength="2000" placeholder="Ex.: Revisei a introdução e corrigi a Tabela 2">
        </label>
        <p class="error" id="save-error" hidden></p>
        <div class="form-buttons">
          <button type="button" class="button" id="save-cancel">Continuar editando</button>
          <button type="submit" class="button primary">Salvar nova versão</button>
        </div>
      </div>
    </form>
    <div class="edit-layout">
      <div id="editor" class="editor-area"></div>
      <aside class="ref-panel box" id="ref-panel" hidden aria-label="Referências"></aside>
    </div>
    <div class="pdf-overlay" id="pdf-overlay" hidden>
      <div class="pdf-overlay-bar"><strong>Como o PDF vai ficar</strong> <span class="muted">(ainda sem salvar)</span>
        <button class="button small" id="pdf-close">Fechar</button></div>
      <div class="pdf-overlay-body" id="pdf-overlay-body"></div>
    </div>
  `;

  // A barra muda de altura quando os botões quebram linha; o painel de referências fica logo abaixo dela.
  const bar = app.querySelector(".edit-bar");
  new ResizeObserver(() => app.style.setProperty("--bar-h", `${bar.offsetHeight}px`)).observe(bar);

  const status = document.getElementById("status");
  const saveButton = document.getElementById("save");
  const markChanged = () => {
    setUnsaved(true);
    saveButton.disabled = false;
    status.textContent = "Mudanças ainda não salvas";
  };
  const area = document.getElementById("editor");
  let editor = null;
  let textarea = null;

  // Imagens recém-escolhidas aparecem na hora, antes de existirem no servidor.
  const serverImages = loadImages(articleId, head.hash);
  const images = (root) => {
    for (const img of root.querySelectorAll("img[data-src]")) {
      const local = newImages.get(img.dataset.src);
      if (local) {
        img.removeAttribute("data-src");
        img.src = local.url;
      }
    }
    return serverImages(root);
  };

  if (code) {
    const source = await apiText(`/articles/${articleId}/versions/${head.hash}/files/main.tex`);
    area.innerHTML = `<div class="box"><div class="box-body">
      <p class="muted">Modo para quem conhece LaTeX: o arquivo principal inteiro, como no Overleaf.</p>
      <textarea class="code" spellcheck="false">${esc(source)}</textarea></div></div>`;
    textarea = area.querySelector("textarea");
    textarea.addEventListener("input", markChanged);
  } else {
    const doc = await api(`/articles/${articleId}/versions/${head.hash}/document`);
    editor = new Editor(area, doc, { onChange: markChanged, loadImages: images });
  }

  for (const button of app.querySelectorAll(".tool")) {
    button.addEventListener("mousedown", (e) => { if (!e.target.closest(".file-tool")) e.preventDefault(); });
  }
  app.querySelectorAll("[data-format]").forEach((b) => { b.onclick = () => editor.format(b.dataset.format); });
  app.querySelectorAll("[data-insert]").forEach((b) => { b.onclick = () => editor.insert(b.dataset.insert); });
  document.getElementById("remove-block").onclick = () => {
    if (!editor.removeCurrent()) status.textContent = "Clique num bloco antes de removê-lo";
  };

  // ----- figuras -----
  const figureInput = document.getElementById("figure-input");
  figureInput.onchange = () => {
    const file = figureInput.files[0];
    figureInput.value = "";
    if (!file) return;
    if (file.size > 8 * 1024 * 1024) {
      status.textContent = "A imagem pode ter no máximo 8 MB";
      return;
    }
    const path = imageName(file);
    newImages.set(path, { file, url: URL.createObjectURL(file) });
    editor.insertFigure(path, "Escreva aqui a legenda da figura");
  };

  // ----- referências -----
  const panel = document.getElementById("ref-panel");
  const taken = () => refs.entries.map((e) => e.key);
  const refsChangedNow = () => {
    refsChanged = true;
    document.getElementById("ref-count").textContent = `(${refs.entries.length})`;
    markChanged();
  };

  function drawPanel(view = "list", editing = null) {
    panel.hidden = false;
    const head = `<header class="box-head"><h2>Referências <span class="count">(${refs.entries.length})</span></h2>
      <button type="button" class="link-button" id="ref-close">fechar</button></header>`;
    if (view === "list") {
      panel.innerHTML = `${head}<div class="box-body">
        <p class="notice-inline">Para citar: clique no texto, no ponto onde a citação deve entrar, e depois em <b>Citar</b> na obra.</p>
        <button type="button" class="button primary small" id="ref-add">+ Adicionar referência</button>
        ${refs.entries.length ? `<ol class="ref-list">${refs.entries.map((e, i) => `
          <li>
            <span class="ref-label">${esc(e.label)}</span>
            <span class="ref-text">${esc(e.text)}</span>
            <span class="ref-meta">${e.cited ? `citada ${e.cited}×` : "ainda não citada"}</span>
            <span class="ref-actions">
              <button type="button" class="button small" data-cite="${i}">Citar</button>
              <button type="button" class="link-button" data-edit="${i}">editar</button>
              <button type="button" class="link-button danger-link" data-delete="${i}">remover</button>
            </span>
          </li>`).join("")}</ol>`
        : `<p class="muted">Nenhuma referência ainda. Adicione as obras que você leu: dá para preencher, colar do Google Acadêmico ou buscar pelo DOI.</p>`}
        <p class="muted small-print">Só as obras citadas no texto aparecem na lista de referências do PDF.</p>
        <p class="error" id="ref-error" hidden></p>
      </div>`;
      panel.querySelectorAll("[data-cite]").forEach((b) => {
        b.onclick = () => {
          const entry = refs.entries[Number(b.dataset.cite)];
          if (!editor.insertCite(entry.key, entry.label)) {
            showError(document.getElementById("ref-error"), new Error("Clique primeiro no texto, no ponto onde a citação deve entrar, e depois em Citar."));
            return;
          }
          entry.cited += 1;
          drawPanel();
        };
      });
      panel.querySelectorAll("[data-edit]").forEach((b) => { b.onclick = () => drawPanel("form", Number(b.dataset.edit)); });
      panel.querySelectorAll("[data-delete]").forEach((b) => {
        b.onclick = () => {
          const entry = refs.entries[Number(b.dataset.delete)];
          const warning = entry.cited ? ` Ela está citada ${entry.cited}× no texto: essas citações vão aparecer como "?" até você apagá-las.` : "";
          if (!confirm(`Remover esta referência?${warning}`)) return;
          refs.entries.splice(Number(b.dataset.delete), 1);
          refsChangedNow();
          drawPanel();
        };
      });
      document.getElementById("ref-add").onclick = () => drawPanel("form");
    } else {
      const entry = editing === null ? { key: "", type: "article", fields: {} } : refs.entries[editing];
      const f = entry.fields;
      const tab = view === "form" ? "fill" : view;
      panel.innerHTML = `${head}<div class="box-body">
        <nav class="view-tabs small-tabs">
          <a href="#" data-tab="form" class="${tab === "fill" ? "active" : ""}">Preencher</a>
          ${editing === null ? `<a href="#" data-tab="bibtex" class="${tab === "bibtex" ? "active" : ""}">Colar BibTeX</a>
          <a href="#" data-tab="doi" class="${tab === "doi" ? "active" : ""}">Buscar pelo DOI</a>` : ""}
        </nav>
        ${tab === "fill" ? `<form class="form" id="ref-form">
          <label>Tipo de obra<select name="type">${Object.entries(refs.types).map(([value, label]) =>
            `<option value="${value}" ${entry.type === value ? "selected" : ""}>${label}</option>`).join("")}</select></label>
          <label>Autores <span class="hint">(um por linha, como "Ana Maria Souza")</span>
            <textarea name="author" rows="3">${esc((f.author || "").split(/\s+and\s+/).join("\n"))}</textarea></label>
          <label>Título<input name="title" required value="${esc(f.title || "")}"></label>
          <label>Ano<input name="year" maxlength="10" value="${esc(f.year || "")}" inputmode="numeric"></label>
          <div id="type-fields"></div>
          <label>DOI <span class="hint">(se tiver)</span><input name="doi" value="${esc(f.doi || "")}" placeholder="10.1145/..."></label>
          <label>Endereço na internet <span class="hint">(se tiver)</span><input name="url" value="${esc(f.url || "")}" placeholder="https://..."></label>
          <p class="error" id="ref-error" hidden></p>
          <div class="form-buttons"><button type="button" class="button" id="ref-back">Voltar</button>
            <button class="button primary" type="submit">${editing === null ? "Adicionar" : "Salvar referência"}</button></div>
        </form>` : tab === "bibtex" ? `<form class="form" id="ref-bibtex">
          <p class="muted">No Google Acadêmico, clique em <b>Citar → BibTeX</b>, copie o texto e cole aqui. Pode colar várias de uma vez.</p>
          <label>BibTeX<textarea name="bibtex" rows="8" required spellcheck="false" class="code-small" placeholder="@article{...}"></textarea></label>
          <p class="error" id="ref-error" hidden></p>
          <div class="form-buttons"><button type="button" class="button" id="ref-back">Voltar</button><button class="button primary" type="submit">Adicionar</button></div>
        </form>` : `<form class="form" id="ref-doi">
          <p class="muted">O DOI fica na página do artigo na revista ou no evento, e começa com 10. Pode colar o link inteiro.</p>
          <label>DOI<input name="doi" required placeholder="10.1145/3290605.3300233"></label>
          <div id="doi-found"></div>
          <p class="error" id="ref-error" hidden></p>
          <div class="form-buttons"><button type="button" class="button" id="ref-back">Voltar</button><button class="button primary" type="submit">Buscar</button></div>
        </form>`}
      </div>`;
      panel.querySelectorAll("[data-tab]").forEach((a) => { a.onclick = (e) => { e.preventDefault(); drawPanel(a.dataset.tab, editing); }; });
      document.getElementById("ref-back").onclick = () => drawPanel();
      const errorBox = document.getElementById("ref-error");
      const add = (found) => {
        for (const item of [].concat(found)) {
          const at = refs.entries.findIndex((e) => e.key === item.key);
          if (editing !== null && at === editing) refs.entries[at] = { ...item, cited: refs.entries[at].cited };
          else refs.entries.push(item);
        }
        refsChangedNow();
        drawPanel();
      };
      if (tab === "fill") {
        const form = document.getElementById("ref-form");
        const drawTypeFields = () => {
          document.getElementById("type-fields").innerHTML = (REF_FIELDS[form.type.value] || []).map(([name, label]) =>
            `<label>${label}<input name="${name}" value="${esc(f[name] || "")}"></label>`).join("");
        };
        form.type.onchange = drawTypeFields;
        drawTypeFields();
        form.onsubmit = async (event) => {
          event.preventDefault();
          const data = Object.fromEntries(new FormData(form));
          const type = data.type;
          delete data.type;
          data.author = data.author.split("\n").map((a) => a.trim()).filter(Boolean).join(" and ");
          const fields = { ...(editing === null ? {} : entry.fields), ...data };
          for (const [key, value] of Object.entries(fields)) if (!String(value).trim()) delete fields[key];
          try {
            add(await postJson("/references/check", { entry: { key: entry.key, type, fields }, taken: taken(), style: refs.style }));
          } catch (error) {
            showError(errorBox, error);
          }
        };
      } else if (tab === "bibtex") {
        const form = document.getElementById("ref-bibtex");
        form.onsubmit = async (event) => {
          event.preventDefault();
          try {
            add(await postJson("/references/parse", { bibtex: form.bibtex.value, taken: taken(), style: refs.style }));
          } catch (error) {
            showError(errorBox, error);
          }
        };
      } else {
        const form = document.getElementById("ref-doi");
        form.onsubmit = async (event) => {
          event.preventDefault();
          const done = busy(form.querySelector("[type=submit]"), "Buscando…");
          const params = new URLSearchParams({ doi: form.doi.value, style: refs.style });
          taken().forEach((k) => params.append("taken", k));
          try {
            const found = await api(`/references/doi?${params}`);
            done();
            document.getElementById("doi-found").innerHTML = `<div class="found-ref"><span>${esc(found.text)}</span>
              <button type="button" class="button small primary" id="doi-add">Adicionar esta</button></div>`;
            document.getElementById("doi-add").onclick = () => add(found);
          } catch (error) {
            done();
            showError(errorBox, error);
          }
        };
      }
    }
    document.getElementById("ref-close").onclick = () => {
      panel.hidden = true;
    };
  }

  // O botão da barra e o aviso no bloco "Referências" do artigo abrem o mesmo painel.
  for (const element of [app.querySelector(".edit-tools"), area]) {
    element.addEventListener("click", (event) => {
      if (event.target.closest("[data-open-references]")) drawPanel();
    });
  }

  // ----- o que vai para o servidor -----
  const draft = async () => {
    const body = code ? { source: textarea.value } : { document: editor.sync() };
    const used = JSON.stringify(body);
    body.images = await Promise.all([...newImages].filter(([path]) => used.includes(path))
      .map(async ([path, { file }]) => ({ path, data: await fileToBase64(file) })));
    if (refsChanged) body.references = refs.entries.map(({ key, type, fields }) => ({ key, type, fields }));
    return { base_version: head.hash, ...body };
  };

  const overlay = document.getElementById("pdf-overlay");
  document.getElementById("preview-button").onclick = async (event) => {
    const done = busy(event.target, "Gerando…");
    try {
      const { pages } = await postJson(`/articles/${articleId}/preview`, await draft());
      const body = document.getElementById("pdf-overlay-body");
      body.innerHTML = `<div class="pdf-pages">${pages.map((src, i) => `
        <figure class="pdf-page"><img src="${src}" alt="Página ${i + 1} de ${pages.length}"><figcaption>${i + 1}</figcaption></figure>`).join("")}</div>`;
      overlay.hidden = false;
      body.scrollTop = 0;
    } catch (error) {
      status.textContent = error.message;
    } finally {
      done();
    }
  };
  document.getElementById("pdf-close").onclick = () => { overlay.hidden = true; };

  const leave = (event) => {
    if (unsaved && !confirm("Você tem mudanças não salvas. Sair e perder essas mudanças?")) event.preventDefault();
    else setUnsaved(false);
  };
  document.getElementById("cancel").onclick = leave;
  document.getElementById("switch-mode").onclick = leave;

  const savePanel = document.getElementById("save-panel");
  saveButton.onclick = () => {
    savePanel.hidden = false;
    savePanel.querySelector("input").focus();
  };
  document.getElementById("save-cancel").onclick = () => { savePanel.hidden = true; };
  savePanel.onsubmit = async (event) => {
    event.preventDefault();
    const message = new FormData(savePanel).get("message");
    const done = busy(savePanel.querySelector("[type=submit]"), "Salvando…");
    try {
      const version = await postJson(`/articles/${articleId}/edits`, { ...(await draft()), message });
      setUnsaved(false);
      go(`#/artigo/${articleId}/${version.hash}/mudancas`);
    } catch (error) {
      done();
      showError(document.getElementById("save-error"), error);
    }
  };
}
