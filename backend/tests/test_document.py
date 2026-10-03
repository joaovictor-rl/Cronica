
from app.demo import PROJECT_DIR, read_project
from app.diff.latex import diff_tex
from app.document.blocks import parse_document, serialize_document
from app.document.inline import parse_inline, to_latex
from app.document.references import annotate, cite_label, load_bibliography

REAL_ARTICLE = (PROJECT_DIR / "main.tex").read_text(encoding="utf-8")

SMALL = r"""\documentclass{article}
\title{Um título com \textit{itálico}}
\author{Ana Souza \and Bruno Lima}
\begin{document}
\maketitle

\begin{abstract}
Resumo curto.
\end{abstract}

\section{Introdução}
\label{sec:intro}
Texto com 50\% de ``aspas'' e uma citação \cite{silva2020}.
Continua na mesma linha lógica.

% um comentário
\begin{itemize}
  \item Primeiro item;
  \item \textbf{Segundo:} item.
\end{itemize}

\begin{figure}[h]
  \centering
  \includegraphics[width=\linewidth]{img/a.png}
  \caption{Legenda antiga}
  \label{fig:a}
\end{figure}

Veja a Figura~\ref{fig:a} e a Seção~\ref{sec:intro}.

\begin{table}[h]
\caption{Tempos}
\label{tab:t}
\begin{tabular}{|c|p{3cm}|}
\hline
\textbf{P} & \textbf{Tempo} \\ \hline
P01 & 2min \\ \hline
\end{tabular}
\end{table}

\bibliography{refs}
\end{document}
"""


def blocks_of(doc, kind):
    return [b for b in doc["blocks"] if b["type"] == kind]


def test_untouched_document_is_written_back_byte_for_byte():
    for source in (SMALL, REAL_ARTICLE):
        assert serialize_document(parse_document(source)) == source


def test_regenerating_every_block_keeps_the_text():
    doc = parse_document(REAL_ARTICLE)
    for block in doc["blocks"]:
        if block["type"] in ("paragraph", "heading", "list", "abstract"):
            del block["src"]
    changes = diff_tex(REAL_ARTICLE, serialize_document(doc))["changes"]
    # A única diferença é um \textit{} vazio que existe no original.
    assert len(changes) == 1 and "\\textit{}" in changes[0]["old"]


def test_structure_of_small_document():
    doc = parse_document(SMALL)
    assert [b["type"] for b in doc["blocks"] if b["type"] != "hidden"] == [
        "abstract", "heading", "paragraph", "list", "figure", "paragraph", "table", "references",
    ]
    [lst] = blocks_of(doc, "list")
    assert lst["items"][1]["spans"][0] == {"t": "Segundo:", "b": True}
    [fig] = blocks_of(doc, "figure")
    assert fig["images"] == [{"path": "img/a.png", "caption": None}]
    [table] = blocks_of(doc, "table")
    assert len(table["rows"]) == 2 and table["columns"][1]["width_cm"] == 3.0


def test_editing_one_paragraph_changes_only_that_sentence():
    doc = parse_document(SMALL)
    paragraph = blocks_of(doc, "paragraph")[0]
    paragraph["spans"] = parse_inline(r"Texto com 60\% de “aspas” e uma citação \cite{silva2020}. Continua na mesma linha lógica.")
    new = serialize_document(doc)
    changes = diff_tex(SMALL, new)["changes"]
    assert len(changes) == 1
    assert {"op": "insert", "text": " 60%"} in changes[0]["words"] or any("60" in w["text"] for w in changes[0]["words"] if w["op"] == "insert")
    assert "\\section{Introdução}\n\\label{sec:intro}" in new


def test_editing_title_and_caption():
    doc = parse_document(SMALL)
    doc["meta"]["title"]["spans"] = [{"t": "Novo título & mais"}]
    blocks_of(doc, "figure")[0]["caption"] = [{"t": "Legenda nova"}]
    new = serialize_document(doc)
    assert r"\title{Novo título \& mais}" in new
    assert r"\caption{Legenda nova}" in new and r"\label{fig:a}" in new


def test_inline_round_trip_and_escaping():
    spans = parse_inline(r"A \textbf{negrito \emph{e itálico}} com \cite{x} e 10\%~ok")
    assert to_latex(spans) == r"A \textbf{negrito }\textbf{\emph{e itálico}} com \cite{x} e 10\%~ok"
    assert to_latex([{"t": "custo: $5 & 100% {x}_y"}]) == r"custo: \$5 \& 100\% \{x\}\_y"


def test_numbering_and_references():
    doc = parse_document(SMALL)
    annotate(doc, {"silva2020": {"type": "article", "fields": {"author": "Silva, Ana and Lima, Bruno", "year": "2020", "title": "T"}}})
    refs = [s["label"] for b in blocks_of(doc, "paragraph") for s in b["spans"] if s.get("kind") in ("ref", "cite")]
    assert refs == ["[Silva and Lima 2020]", "1", "1"]
    assert doc["bibliography"][0]["text"].startswith("Silva, A. and Lima, B. (2020). T.")


def test_real_article_references_match_sbc_style():
    files = read_project()
    doc = parse_document(REAL_ARTICLE)
    annotate(doc, load_bibliography(doc, "main.tex", files))
    labels = {s["label"] for b in doc["blocks"] for s in b.get("spans", []) if s.get("kind") == "cite"}
    assert "[de Abreu Cybis et al. 2015]" in labels and "[Barbosa et al. 2021]" in labels
    assert [b["number"] for b in doc["blocks"] if b["type"] == "figure"] == [str(n) for n in range(1, 9)]


def test_cite_label_for_organizations_and_particles():
    assert cite_label({"fields": {"author": "{Ministério da Saúde}", "year": "2026"}}, "x") == "Ministério da Saúde 2026"
    assert cite_label({"fields": {"author": "Clarisse Sieckenius de Souza", "year": "2005"}}, "x") == "de Souza 2005"
