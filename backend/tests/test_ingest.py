import io
import zipfile

import pytest

from app import ingest
from app.ingest import ZipRejected, decode_text, extract_zip
from tests.conftest import make_zip


def test_ignores_generated_files_and_macos_junk():
    files = extract_zip(make_zip({
        "main.tex": "Olá.", "main.aux": "x", "main.log": "x", "main.synctex.gz": b"x",
        "__MACOSX/._main.tex": b"x", "refs.bib": "@article{a, title={T}}", "main.bbl": "x",
    }))
    assert set(files) == {"main.tex", "refs.bib"}


@pytest.mark.parametrize("bad_path", ["../fora.tex", "/etc/passwd", "a/../../fora.tex", "C:/windows.tex", "pasta\\arquivo.tex"])
def test_rejects_zip_slip(bad_path):
    with pytest.raises(ZipRejected):
        extract_zip(make_zip({"main.tex": "ok", bad_path: "x"}))


def test_rejects_too_many_files(monkeypatch):
    monkeypatch.setattr(ingest, "MAX_FILES", 3)
    with pytest.raises(ZipRejected, match="mais de 3"):
        extract_zip(make_zip({f"f{i}.tex": "x" for i in range(4)}))


def test_rejects_large_file_even_if_compressed_small(monkeypatch):
    monkeypatch.setattr(ingest, "MAX_FILE_BYTES", 1000)
    with pytest.raises(ZipRejected, match="limite"):
        extract_zip(make_zip({"grande.tex": "a" * 5000}))


def test_rejects_total_size(monkeypatch):
    monkeypatch.setattr(ingest, "MAX_TOTAL_BYTES", 1000)
    with pytest.raises(ZipRejected, match="total"):
        extract_zip(make_zip({"a.tex": "a" * 600, "b.tex": "b" * 600}))


def test_rejects_invalid_and_empty_zip():
    with pytest.raises(ZipRejected, match="zip válido"):
        extract_zip(b"isto nao e um zip")
    with pytest.raises(ZipRejected, match="nenhum arquivo"):
        extract_zip(make_zip({"main.aux": "x"}))


def test_strips_single_root_folder():
    files = extract_zip(make_zip({"meu-artigo/main.tex": "a", "meu-artigo/fig/a.png": b"\x89PNG"}))
    assert set(files) == {"main.tex", "fig/a.png"}


def test_decodes_latin1_fallback():
    assert decode_text("ação".encode("latin-1")) == "ação"


class LegacyName(zipfile.ZipInfo):
    """Nome gravado em bytes crus, sem a marca de UTF-8, como fazem o Windows e o zip do Linux."""

    def __init__(self, raw: bytes):
        super().__init__(raw.decode("latin-1"))
        self.raw = raw

    def _encodeFilenameFlags(self):
        return self.raw, self.flag_bits & ~0x800


def test_accented_names_from_zips_without_utf8_flag():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr(LegacyName("vacinação.pdf".encode("utf-8")), b"x")
        zf.writestr(LegacyName("legenda_ção.png".encode("cp850")), b"x")
    assert set(extract_zip(buffer.getvalue())) == {"vacinação.pdf", "legenda_ção.png"}
