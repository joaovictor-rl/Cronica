// Mostra o artigo para leitura e as diferenças entre versões.

export function esc(text) {
  return String(text ?? "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  })[c]);
}

export function spansHtml(spans = []) {
  return spans.map((span) => {
    if (span.br) return "<br>";
    let html;
    if ("t" in span) {
      html = esc(span.t);
    } else {
      const label = esc(span.label);
      switch (span.kind) {
        case "comment":
        case "label":
          return "";
        case "footnote":
          html = `<sup class="footnote-mark" title="${esc(span.text)}">${label}</sup>`;
          break;
        case "sup":
          html = `<sup>${label}</sup>`;
          break;
        case "math":
          html = `<i class="math">${label}</i>`;
          break;
        case "url":
          html = `<a href="${esc(span.href)}" target="_blank" rel="noopener">${label}</a>`;
          break;
        case "cite":
          html = `<span class="cite">${label}</span>`;
          break;
        default:
          html = label;
      }
    }
    if (span.i) html = `<em>${html}</em>`;
    if (span.b) html = `<strong>${html}</strong>`;
    return html;
  }).join("");
}

const LETTERS = "abcdefghijklmnopqrstuvwxyz";

export function abstractLabel(doc, block) {
  if (block.env === "resumo") return "Resumo";
  if (block.env === "IEEEkeywords") return "Index Terms";
  return doc.language === "en" ? "Abstract" : "Resumo";
}

export function figureHtml(block) {
  const many = block.images.length > 1;
  const images = block.images.map((image, i) => `
    <figure class="${many ? "subfigure" : "single"}">
      <img data-src="${esc(image.path)}" alt="${esc(image.caption ? plain(image.caption) : "Figura")}">
      ${image.caption ? `<figcaption>(${LETTERS[i]}) ${spansHtml(image.caption)}</figcaption>` : ""}
    </figure>
  `).join("");
  return `
    <div class="figure-images ${many ? "grid" : ""}">${images}</div>
    ${block.caption ? `<p class="caption"><b>Figura ${esc(block.number)}.</b> ${spansHtml(block.caption)}</p>` : ""}
    ${block.source && block.source.length ? `<p class="figure-source"><b>Fonte:</b> ${spansHtml(block.source)}</p>` : ""}
  `;
}

export function tableHtml(block, captionHtml = null, label = `Tabela ${block.number}.`) {
  const caption = captionHtml ?? (block.caption ? spansHtml(block.caption) : "");
  const aligns = (block.columns || []).map((c) => c.align || "left");
  return `
    ${caption ? `<p class="caption"><b>${esc(label)}</b> ${caption}</p>` : ""}
    <div class="table-scroll">
      <table class="paper-table">
        ${block.rows.map((row) => `<tr>${row.map((cell, i) => `<td style="text-align:${aligns[i] || "left"}">${spansHtml(cell)}</td>`).join("")}</tr>`).join("")}
      </table>
    </div>
    ${block.note && block.note.length ? `<p class="table-note">${spansHtml(block.note)}</p>` : ""}
  `;
}

function plain(spans = []) {
  return spans.map((s) => ("t" in s ? s.t : s.br ? " " : s.kind === "comment" ? "" : s.label || "")).join("").trim();
}

// ---------- diferenças ----------

const FILE_STATUS = { modified: "alterado", added: "novo", removed: "removido", renamed: "renomeado" };

function count(n, one, many) {
  return `${n} ${n === 1 ? one : many}`;
}

function mark(tag, text) {
  const [, space, word] = text.match(/^(\s*)([\s\S]*)$/);
  return `${space}<${tag}>${esc(word)}</${tag}>`;
}

// Deixa a frase legível para quem não conhece LaTeX: \% vira %, ~ vira espaço, \section{X} vira um rótulo.
const HEADING = /^\\(sub)*section\*?\{([\s\S]*)\}$/;

function humanize(text) {
  return text.replace(/\\([%&_#$])/g, "$1").replace(/~/g, " ");
}

function sentenceTag(text, sentenceLabel, headingLabel) {
  const heading = text.match(HEADING);
  return heading ? [headingLabel, heading[2]] : [sentenceLabel, text];
}

function texChanges(diff) {
  const s = diff.stats;
  const summary = [
    s.modified && count(s.modified, "frase alterada", "frases alteradas"),
    s.added && count(s.added, "frase nova", "frases novas"),
    s.removed && count(s.removed, "frase removida", "frases removidas"),
  ].filter(Boolean).join(" · ");
  if (!diff.changes.length) return `<p class="muted">Só mudaram comentários ou quebras de linha; o texto é o mesmo.</p>`;
  return `
    <p class="summary">${summary}</p>
    <div class="changes">
      ${diff.changes.map((c) => {
        if (c.op === "insert") {
          const [tag, text] = sentenceTag(c.new, "Frase nova", "Título de seção novo");
          return `<div class="change insert"><span class="tag">${tag}</span><p class="prose"><ins>${esc(humanize(text))}</ins></p></div>`;
        }
        if (c.op === "delete") {
          const [tag, text] = sentenceTag(c.old, "Frase removida", "Título de seção removido");
          return `<div class="change delete"><span class="tag">${tag}</span><p class="prose"><del>${esc(humanize(text))}</del></p></div>`;
        }
        const words = c.words.map((w) => (w.op === "insert" ? mark("ins", humanize(w.text)) : w.op === "delete" ? mark("del", humanize(w.text)) : esc(humanize(w.text)))).join("");
        return `<div class="change modify"><span class="tag">${c.only_markup ? "Só citação ou comando LaTeX" : "Frase alterada"}</span><p class="prose">${words}</p></div>`;
      }).join("")}
    </div>
  `;
}

function bibChanges(diff) {
  if (!diff.changes.length) return `<p class="muted">Só a formatação do arquivo mudou; as referências são as mesmas.</p>`;
  return `<div class="changes">${diff.changes.map((c) => {
    if (c.op === "insert") return `<div class="change insert"><span class="tag">Referência nova</span><p><code>${esc(c.key)}</code> — ${esc(c.new.fields.title || "sem título")}</p></div>`;
    if (c.op === "delete") return `<div class="change delete"><span class="tag">Referência removida</span><p><code>${esc(c.key)}</code> — ${esc(c.old.fields.title || "sem título")}</p></div>`;
    return `<div class="change modify"><span class="tag">Referência alterada</span><p><code>${esc(c.key)}</code></p>
      <table class="fields"><thead><tr><th>Campo</th><th>Antes</th><th>Depois</th></tr></thead><tbody>
      ${Object.entries(c.fields).map(([name, v]) => `<tr><td>${esc(name)}</td><td><del>${esc(v.old ?? "—")}</del></td><td><ins>${esc(v.new ?? "—")}</ins></td></tr>`).join("")}
      </tbody></table></div>`;
  }).join("")}</div>`;
}

function lineChanges(diff) {
  const lines = diff.patch.split("\n").map((line) => {
    const kind = line.startsWith("+") ? "add" : line.startsWith("-") ? "del" : line.startsWith("@@") ? "hunk" : "";
    return `<span class="line ${kind}">${esc(line)}</span>`;
  });
  return `<pre class="patch">${lines.join("\n")}</pre>`;
}

export function fileDiffHtml(file) {
  let body;
  if (file.status === "added") body = `<p class="muted">Arquivo novo nesta versão.</p>`;
  else if (file.status === "removed") body = `<p class="muted">Arquivo removido nesta versão.</p>`;
  else if (file.status === "renamed") body = `<p class="muted">Antes se chamava <code>${esc(file.old_path)}</code>. O conteúdo não mudou.</p>`;
  else if (!file.diff) body = `<p class="muted">O arquivo mudou, mas não é texto, então não dá para mostrar a diferença.</p>`;
  else if (file.diff.kind === "tex") body = texChanges(file.diff);
  else if (file.diff.kind === "bib") body = bibChanges(file.diff);
  else body = lineChanges(file.diff);
  return `
    <article class="card file">
      <header class="file-header"><code>${esc(file.path)}</code><span class="badge ${file.status}">${FILE_STATUS[file.status]}</span></header>
      ${body}
    </article>
  `;
}
