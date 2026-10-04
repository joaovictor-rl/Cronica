// Editor visual: cada parágrafo, título e item é um campo editável. O LaTeX fica escondido.
import { abstractLabel, esc, figureHtml, tableHtml } from "./render.js";

const CHIP_TEXT = { comment: "nota", label: "rótulo", cmd: "LaTeX", env: "LaTeX", group: "LaTeX" };
const CHIP_HINT = {
  cite: "Citação. Para tirar, apague como se fosse uma palavra.",
  ref: "Referência a uma seção, figura ou tabela.",
  footnote: "Nota de rodapé",
  math: "Fórmula",
};

function chipHtml(span) {
  const data = { ...span };
  delete data.b;
  delete data.i;
  // Comandos sem texto visível (\vspace, \noindent...) aparecem só como um marcador discreto.
  const quiet = span.kind === "cmd" && !span.label.trim();
  const text = quiet ? "·" : span.label || CHIP_TEXT[span.kind] || "LaTeX";
  const hint = span.kind === "footnote" ? `Nota: ${span.text}` : CHIP_HINT[span.kind] || span.raw;
  return `<span class="chip chip-${esc(span.kind)}${quiet ? " chip-quiet" : ""}" contenteditable="false" data-span="${esc(JSON.stringify(data))}" title="${esc(hint)}">${esc(text)}</span>`;
}

// O espaço inseparável (~ no LaTeX) vira um elemento próprio; espaços que o navegador insere ao digitar não.
const NBSP = `<span class="nbsp" contenteditable="false" data-span='{"raw":"~","kind":"nbsp","label":"\u00a0"}'>&nbsp;</span>`;

function textHtml(text) {
  return text.split("\u00a0").map(esc).join(NBSP);
}

function editableHtml(spans = []) {
  return spans.map((span) => {
    if (span.br) return "<br>";
    let html = "t" in span ? textHtml(span.t) : span.kind === "nbsp" ? NBSP : chipHtml(span);
    if (span.i) html = `<em data-cmd="${esc(span.i)}">${html}</em>`;
    if (span.b) html = `<strong>${html}</strong>`;
    return html;
  }).join("");
}

export function readSpans(element) {
  const spans = [];
  const walk = (node, fmt) => {
    for (const child of node.childNodes) {
      if (child.nodeType === Node.TEXT_NODE) {
        spans.push({ t: child.nodeValue, ...fmt });
        continue;
      }
      if (child.nodeType !== Node.ELEMENT_NODE) continue;
      if (child.dataset.span) {
        const span = JSON.parse(child.dataset.span);
        spans.push({ ...span, ...fmt });
        continue;
      }
      if (child.tagName === "BR") {
        spans.push({ br: true });
        continue;
      }
      const inner = { ...fmt };
      if (child.tagName === "STRONG" || child.tagName === "B") inner.b = true;
      if (child.tagName === "EM" || child.tagName === "I") inner.i = child.dataset.cmd || "textit";
      walk(child, inner);
    }
  };
  walk(element, {});

  const merged = [];
  for (const span of spans) {
    const last = merged[merged.length - 1];
    if ("t" in span && last && "t" in last && Boolean(last.b) === Boolean(span.b) && last.i === span.i) last.t += span.t;
    else merged.push({ ...span });
  }
  for (const span of merged) {
    if ("t" in span) span.t = span.t.replace(/\u00a0/g, " ").replace(/[ \t\n]+/g, " ");
  }
  while (merged.length && merged[merged.length - 1].br) merged.pop();
  if (merged.length && "t" in merged[0]) merged[0].t = merged[0].t.trimStart();
  if (merged.length && "t" in merged[merged.length - 1]) merged[merged.length - 1].t = merged[merged.length - 1].t.trimEnd();
  return merged.filter((s) => !("t" in s) || s.t);
}

function caretAtStart(element) {
  const selection = getSelection();
  if (!selection.rangeCount || !selection.isCollapsed) return false;
  const range = document.createRange();
  range.selectNodeContents(element);
  range.setEnd(selection.anchorNode, selection.anchorOffset);
  return range.toString().length === 0 && !range.cloneContents().querySelector?.("[data-span]");
}

function placeCaret(element, where) {
  element.focus();
  const range = document.createRange();
  range.selectNodeContents(element);
  range.collapse(where === "start");
  const selection = getSelection();
  selection.removeAllRanges();
  selection.addRange(range);
}

function headingNumbers(blocks) {
  const counters = [0, 0, 0, 0];
  const numbers = {};
  blocks.forEach((block, index) => {
    if (block.type !== "heading" || block.star || block.level < 1 || block.level > 3) return;
    counters[block.level] += 1;
    for (let deeper = block.level + 1; deeper < counters.length; deeper++) counters[deeper] = 0;
    numbers[index] = counters.slice(1, block.level + 1).join(".");
  });
  return numbers;
}

export class Editor {
  // Na ABNT a legenda da figura fica em cima da imagem.
  get abnt() {
    return this.doc.citation_style === "abnt";
  }

  constructor(root, doc, { onChange, loadImages }) {
    this.root = root;
    this.doc = structuredClone(doc);
    this.onChange = onChange;
    this.loadImages = loadImages;
    this.current = null;
    this.root.addEventListener("keydown", (e) => this.keydown(e));
    this.root.addEventListener("input", () => this.onChange());
    this.root.addEventListener("paste", (e) => this.paste(e));
    // Guarda onde o cursor estava no texto, para o botão "Citar" inserir a citação ali mesmo.
    this.lastRange = null;
    document.addEventListener("selectionchange", () => {
      const selection = document.getSelection();
      if (!selection.rangeCount) return;
      const range = selection.getRangeAt(0);
      const field = range.startContainer.parentElement?.closest?.("[contenteditable=true]") ||
        (range.startContainer.nodeType === Node.ELEMENT_NODE && range.startContainer.closest?.("[contenteditable=true]"));
      if (field && this.root.contains(field) && field.tagName !== "TEXTAREA") this.lastRange = range.cloneRange();
    });
    this.root.addEventListener("focusin", (e) => {
      const block = e.target.closest("[data-index]");
      this.current = block ? Number(block.dataset.index) : null;
      this.root.querySelectorAll(".ed-block.focused").forEach((el) => el.classList.remove("focused"));
      block?.classList.add("focused");
    });
    this.render();
  }

  // ---------- desenho ----------

  render(focus) {
    const meta = this.doc.meta || {};
    const numbers = headingNumbers(this.doc.blocks);
    const field = (name, cls, placeholder) => meta[name]
      ? `<div class="${cls}" contenteditable="true" data-path="meta.${name}" data-placeholder="${placeholder}">${editableHtml(meta[name].spans)}</div>`
      : "";

    this.root.innerHTML = `
      <article class="paper editing">
        ${field("title", "paper-title", "Título do artigo")}
        ${field("author", "paper-authors", "Autores")}
        ${field("address", "paper-address", "Instituição")}
        ${this.doc.blocks.map((block, index) => this.blockHtml(block, index, numbers[index])).join("")}
      </article>
    `;
    this.loadImages(this.root);
    if (focus) {
      const target = this.root.querySelector(`[data-path="${focus.path}"]`);
      if (target) placeCaret(target, focus.where || "start");
    }
  }

  blockHtml(block, index, number) {
    const path = `b.${index}`;
    const wrap = (inner, extra = "") => `<div class="ed-block ed-${block.type} ${extra}" data-index="${index}">${inner}</div>`;
    switch (block.type) {
      case "paragraph":
        return wrap(`<p contenteditable="true" data-path="${path}" data-placeholder="Escreva aqui…">${editableHtml(block.spans)}</p>`);
      case "heading": {
        const level = Math.min((block.level || 1) + 1, 5);
        return wrap(`<h${level}>${number ? `<span class="number" contenteditable="false">${number}.</span> ` : ""}<span contenteditable="true" data-path="${path}" data-placeholder="Título da seção">${editableHtml(block.spans)}</span></h${level}>`);
      }
      case "abstract":
        return wrap(`<div class="paper-abstract"><p class="abstract-label">${abstractLabel(this.doc, block)}</p>
          ${block.paragraphs.map((p, i) => `<p contenteditable="true" data-path="${path}.p.${i}" data-placeholder="Resumo do artigo">${editableHtml(p)}</p>`).join("")}</div>`);
      case "list": {
        const tag = block.env === "enumerate" ? "ol" : "ul";
        return wrap(`<${tag}>${block.items.map((item, i) => `<li contenteditable="true" data-path="${path}.i.${i}" data-placeholder="Item da lista">${editableHtml(item.spans)}</li>`).join("")}</${tag}>`);
      }
      case "figure":
      case "table": {
        const editable = block.cap ? `<span contenteditable="true" data-path="${path}.cap" data-placeholder="Legenda">${editableHtml(block.caption)}</span>` : null;
        if (block.type === "table") {
          return wrap(`<div class="paper-figure">${tableHtml(block, editable)}<p class="ed-hint">Para mudar as células da tabela, use o modo código LaTeX.</p></div>`);
        }
        const html = figureHtml({ ...block, caption: null, source: null });
        const caption = block.caption ? `<p class="caption"><b>Figura ${esc(block.number || "")}.</b> ${editable ?? ""}</p>` : "";
        const source = `<p class="figure-source"><b>Fonte:</b> <span contenteditable="true" data-path="${path}.source"
          data-placeholder="de onde veio a imagem, por exemplo: elaborado pelos autores (2026)">${editableHtml(block.source || [])}</span></p>`;
        return wrap(`<div class="paper-figure">${this.abnt ? caption + html : html + caption}${source}</div>`);
      }
      case "raw":
        return wrap(`<details class="ed-raw"><summary>Trecho em LaTeX (avançado)</summary>
          <textarea data-path="${path}.src" spellcheck="false" rows="${Math.min(block.src.split("\n").length + 1, 14)}">${esc(block.src)}</textarea></details>`);
      case "references":
        return wrap(`<div class="ed-note"><b>Referências</b> — a lista sai sozinha, com as obras citadas no texto.
          <button type="button" class="link-button" data-open-references>Ver e adicionar referências</button></div>`);
      default:
        return "";
    }
  }

  // ---------- leitura dos campos ----------

  sync() {
    for (const element of this.root.querySelectorAll("[data-path]")) {
      const [scope, a, b, c] = element.dataset.path.split(".");
      if (scope === "meta") {
        this.doc.meta[a].spans = readSpans(element);
        continue;
      }
      const block = this.doc.blocks[Number(a)];
      if (b === "src") block.src = element.value;
      else if (b === "cap") block.caption = readSpans(element);
      else if (b === "source") block.source = readSpans(element);
      else if (b === "p") block.paragraphs[Number(c)] = readSpans(element);
      else if (b === "i") block.items[Number(c)].spans = readSpans(element);
      else block.spans = readSpans(element);
    }
    return this.doc;
  }

  // ---------- teclado ----------

  keydown(event) {
    const element = event.target.closest?.("[contenteditable=true]");
    if (!element) return;
    const [scope, a, b, c] = element.dataset.path.split(".");
    if ((event.ctrlKey || event.metaKey) && ["b", "i"].includes(event.key.toLowerCase())) {
      event.preventDefault();
      document.execCommand(event.key.toLowerCase() === "b" ? "bold" : "italic");
      return;
    }
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      if (scope === "meta" || b === "cap") return;
      this.split(element, Number(a), b, Number(c));
    } else if (event.key === "Backspace" && caretAtStart(element) && scope !== "meta" && b !== "cap") {
      if (this.mergeBack(element, Number(a), b, Number(c))) event.preventDefault();
    }
  }

  takeTail(element) {
    const selection = getSelection();
    const range = selection.getRangeAt(0);
    range.deleteContents();
    const tail = document.createRange();
    tail.setStart(range.endContainer, range.endOffset);
    tail.setEnd(element, element.childNodes.length);
    const holder = document.createElement("div");
    holder.append(tail.extractContents());
    return readSpans(holder);
  }

  split(element, index, part, sub) {
    const tailSpans = this.takeTail(element);
    this.sync();
    const block = this.doc.blocks[index];
    if (part === "i") {
      block.items.splice(sub + 1, 0, { opt: null, spans: tailSpans });
      this.changed({ path: `b.${index}.i.${sub + 1}` });
    } else if (part === "p") {
      block.paragraphs.splice(sub + 1, 0, tailSpans);
      this.changed({ path: `b.${index}.p.${sub + 1}` });
    } else {
      this.doc.blocks.splice(index + 1, 0, { type: "paragraph", spans: tailSpans });
      this.changed({ path: `b.${index + 1}` });
    }
  }

  mergeBack(element, index, part, sub) {
    this.sync();
    const block = this.doc.blocks[index];
    if (part === "i") {
      if (block.items[sub].spans.length) return false;
      block.items.splice(sub, 1);
      if (!block.items.length) {
        this.doc.blocks.splice(index, 1);
        this.changed(this.previousField(index, "end"));
      } else {
        this.changed({ path: sub ? `b.${index}.i.${sub - 1}` : `b.${index}.i.0`, where: "end" });
      }
      return true;
    }
    if (part === "p") {
      if (sub === 0) return false;
      block.paragraphs[sub - 1] = block.paragraphs[sub - 1].concat(block.paragraphs[sub]);
      block.paragraphs.splice(sub, 1);
      this.changed({ path: `b.${index}.p.${sub - 1}`, where: "end" });
      return true;
    }
    const previous = this.previousVisible(index);
    if (block.type === "paragraph" && previous !== null && this.doc.blocks[previous].type === "paragraph") {
      this.doc.blocks[previous].spans = this.doc.blocks[previous].spans.concat(block.spans);
      this.doc.blocks.splice(index, 1);
      this.changed({ path: `b.${previous}`, where: "end" });
      return true;
    }
    if (!block.spans.length) {
      this.doc.blocks.splice(index, 1);
      this.changed(this.previousField(index, "end"));
      return true;
    }
    return false;
  }

  previousVisible(index) {
    for (let i = index - 1; i >= 0; i--) {
      if (this.doc.blocks[i].type !== "hidden") return i;
    }
    return null;
  }

  previousField(index, where) {
    const previous = this.previousVisible(index);
    if (previous === null) return null;
    const block = this.doc.blocks[previous];
    if (block.type === "list") return { path: `b.${previous}.i.${block.items.length - 1}`, where };
    if (block.type === "abstract") return { path: `b.${previous}.p.${block.paragraphs.length - 1}`, where };
    return { path: `b.${previous}`, where };
  }

  paste(event) {
    if (!event.target.closest?.("[contenteditable=true]")) return;
    event.preventDefault();
    const text = event.clipboardData.getData("text/plain").replace(/\s*\n\s*/g, " ");
    document.execCommand("insertText", false, text);
  }

  changed(focus) {
    this.render(focus);
    this.onChange();
  }

  // ---------- botões da barra ----------

  format(command) {
    document.execCommand(command);
    this.onChange();
  }

  insert(kind) {
    this.sync();
    const at = this.current === null ? this.doc.blocks.length : this.current + 1;
    const blocks = {
      paragraph: { type: "paragraph", spans: [] },
      section: { type: "heading", cmd: "section", level: 1, star: false, spans: [] },
      subsection: { type: "heading", cmd: "subsection", level: 2, star: false, spans: [] },
      list: { type: "list", env: "itemize", items: [{ opt: null, spans: [] }] },
    };
    this.doc.blocks.splice(at, 0, blocks[kind]);
    this.current = at;
    this.changed({ path: kind === "list" ? `b.${at}.i.0` : `b.${at}` });
  }

  // Cita uma referência onde o cursor estava. Devolve false se a pessoa ainda não clicou no texto.
  insertCite(key, label) {
    const range = this.lastRange;
    if (!range || !this.root.contains(range.startContainer)) return false;
    const holder = document.createElement("span");
    holder.innerHTML = chipHtml({ raw: `\\cite{${key}}`, kind: "cite", keys: [key], label });
    const chip = holder.firstChild;
    const space = document.createTextNode("\u00a0");
    range.collapse(false);
    // Clicou no meio de uma palavra: a citação vai para o fim dela, não a corta ao meio.
    if (range.startContainer.nodeType === Node.TEXT_NODE) {
      const text = range.startContainer.data;
      let end = range.startOffset;
      while (end < text.length && /[\p{L}\p{N}]/u.test(text[end])) end += 1;
      range.setStart(range.startContainer, end);
      range.collapse(true);
    }
    const before = range.startContainer.nodeType === Node.TEXT_NODE ? range.startContainer.data.slice(0, range.startOffset) : "";
    const next = range.startContainer.nodeType === Node.TEXT_NODE ? range.startContainer.data.slice(range.startOffset) : "";
    range.insertNode(chip);
    if (before && !/\s$/.test(before)) chip.before(document.createTextNode(" "));
    // Antes de ponto ou vírgula a citação fica colada neles: "computacionais [Silva 2020]."
    if (/^[\s.,;:!?)]/.test(next)) space.data = "";
    chip.after(space);
    const selection = document.getSelection();
    const after = document.createRange();
    after.setStartAfter(space);
    selection.removeAllRanges();
    selection.addRange(after);
    this.lastRange = after.cloneRange();
    this.onChange();
    return true;
  }

  // Figura nova logo depois do bloco atual, com a imagem já escolhida e uma legenda.
  insertFigure(path, caption) {
    this.sync();
    const label = "fig:" + path.replace(/^.*\//, "").replace(/\.[a-z]+$/, "");
    const placeholder = "Legenda";
    const image = `  \\includegraphics[width=0.8\\textwidth]{${path}}\n`;
    const captionLines = `  \\caption{${placeholder}}\n  \\label{${label}}\n`;
    // Na ABNT a legenda vem em cima da imagem; nos outros formatos, embaixo.
    const src = `\\begin{figure}[htbp]\n  \\centering\n${this.abnt ? captionLines + image : image + captionLines}\\end{figure}`;
    const start = src.indexOf("\\caption{") + 9;
    const at = this.current === null ? this.doc.blocks.length : this.current + 1;
    this.doc.blocks.splice(at, 0, {
      type: "figure", src, images: [{ path, caption: null }], caption: [{ t: caption }],
      cap: [start, start + placeholder.length], label, source: [],
    });
    this.current = at;
    this.changed({ path: `b.${at}.cap` });
  }

  removeCurrent() {
    if (this.current === null) return false;
    this.sync();
    this.doc.blocks.splice(this.current, 1);
    const focus = this.previousField(this.current, "end");
    this.current = null;
    this.changed(focus);
    return true;
  }
}
