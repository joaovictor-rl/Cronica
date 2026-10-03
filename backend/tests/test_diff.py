from app.diff.bib import diff_bib, parse_bib
from app.diff.latex import diff_tex, units

TEXT = r"""
\section{Introdução}
A música amazônica é pouco estudada. Este trabalho propõe um método novo,
conforme Silva et al. \cite{silva2020}. Ver Fig.~\ref{fig:a} para detalhes.

% comentário que não conta
O método foi testado em 30 gravações.
"""


def test_units_split_sentences_and_structure():
    assert units(TEXT) == [
        r"\section{Introdução}",
        "A música amazônica é pouco estudada.",
        r"Este trabalho propõe um método novo, conforme Silva et al. \cite{silva2020}.",
        r"Ver Fig.~\ref{fig:a} para detalhes.",
        "O método foi testado em 30 gravações.",
    ]


def test_rewrapping_lines_is_not_a_change():
    rewrapped = TEXT.replace("método novo,\nconforme", "método\nnovo, conforme")
    assert diff_tex(TEXT, rewrapped)["changes"] == []


def test_comment_edits_are_not_changes():
    assert diff_tex(TEXT, TEXT.replace("que não conta", "editado"))["changes"] == []


def test_word_change_marks_only_that_sentence():
    result = diff_tex(TEXT, TEXT.replace("30 gravações", "45 gravações"))
    [change] = result["changes"]
    assert change["op"] == "modify"
    assert {"op": "delete", "text": " 30"} in change["words"]
    assert {"op": "insert", "text": " 45"} in change["words"]
    assert change["only_markup"] is False


def test_citation_change_is_flagged_as_markup():
    result = diff_tex(TEXT, TEXT.replace(r"\cite{silva2020}", r"\cite{silva2020,costa2021}"))
    [change] = result["changes"]
    assert change["only_markup"] is True
    assert {"op": "insert", "text": r" \cite{silva2020,costa2021}"} in change["words"]


def test_inserted_and_removed_sentences():
    new = TEXT.replace("é pouco estudada.", "é pouco estudada. Há poucos acervos digitais.")
    new = new.replace(r"Ver Fig.~\ref{fig:a} para detalhes.", "")
    stats = diff_tex(TEXT, new)["stats"]
    assert (stats["added"], stats["removed"], stats["modified"]) == (1, 1, 0)


BIB = """
@article{silva2020,
  title = {Música e {Amazônia}},
  author = "Silva, A.",
  year = 2020
}
@comment{ignorar}
@book{costa2021, title={Acervos}, year={2021}}
"""


def test_parse_bib_handles_braces_quotes_and_numbers():
    entries = parse_bib(BIB)
    assert set(entries) == {"silva2020", "costa2021"}
    assert entries["silva2020"]["fields"] == {"title": "Música e {Amazônia}", "author": "Silva, A.", "year": "2020"}


def test_bib_diff_by_entry():
    new = BIB.replace("year = 2020", "year = 2021").replace("@book{costa2021, title={Acervos}, year={2021}}", "")
    new += "@misc{novo2024, title={Novo}}"
    changes = {c["key"]: c for c in diff_bib(BIB, new)["changes"]}
    assert changes["silva2020"]["fields"] == {"year": {"old": "2020", "new": "2021"}}
    assert changes["costa2021"]["op"] == "delete"
    assert changes["novo2024"]["op"] == "insert"


def test_word_diff_rebuilds_both_sentences():
    old = r"Coletamos 30 gravações, conforme \cite{a}."
    new = r"Coletamos 45 gravações novas, conforme \cite{a}."
    [change] = diff_tex(old, new)["changes"]
    words = change["words"]
    assert "".join(w["text"] for w in words if w["op"] != "insert") == old
    assert "".join(w["text"] for w in words if w["op"] != "delete") == new


def test_insertion_at_sentence_start_keeps_the_space():
    [change] = diff_tex("Para realizar o mapeamento.", "Hoje, Para realizar o mapeamento.")["changes"]
    words = change["words"]
    assert "".join(w["text"] for w in words if w["op"] != "delete") == "Hoje, Para realizar o mapeamento."
    assert "".join(w["text"] for w in words if w["op"] != "insert") == "Para realizar o mapeamento."
