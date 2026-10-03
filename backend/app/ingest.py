import io
import unicodedata
import zipfile
from pathlib import PurePosixPath

MAX_ZIP_BYTES = 50 * 2**20
MAX_FILES = 2000
MAX_FILE_BYTES = 25 * 2**20
MAX_TOTAL_BYTES = 200 * 2**20
GENERATED = (".aux", ".log", ".out", ".toc", ".synctex.gz", ".fls", ".fdb_latexmk", ".blg", ".bbl", ".lof", ".lot", ".run.xml")
TEXT_EXTENSIONS = {".tex", ".bib", ".sty", ".cls", ".bst", ".txt", ".md", ".cfg", ".def"}


class ZipRejected(ValueError):
    pass


def is_ignored(path: str) -> bool:
    parts = path.split("/")
    if "__MACOSX" in parts or parts[-1] in {".DS_Store", "Thumbs.db"}:
        return True
    return parts[-1].lower().endswith(GENERATED)  # arquivos que o LaTeX gera sozinho


def safe_path(raw: str) -> str:
    if "\\" in raw or raw.startswith("/") or (len(raw) > 1 and raw[1] == ":"):
        raise ZipRejected(f"O zip tem um arquivo num local não permitido ({raw}). Exporte o projeto de novo pelo Overleaf.")
    parts = PurePosixPath(raw).parts
    if ".." in parts:
        raise ZipRejected(f"O zip tem um arquivo num local não permitido ({raw}). Exporte o projeto de novo pelo Overleaf.")
    return "/".join(p for p in parts if p != ".")


def entry_name(info: zipfile.ZipInfo) -> str:
    """Nome do arquivo no zip. Zips feitos no Windows ou no Linux nem sempre avisam que o nome é UTF-8."""
    name = info.filename
    if not info.flag_bits & 0x800:
        raw = name.encode("cp437")
        for encoding in ("utf-8", "cp850"):
            try:
                name = raw.decode(encoding)
                break
            except UnicodeDecodeError:
                continue
    return unicodedata.normalize("NFC", name)


def read_limited(zf: zipfile.ZipFile, info: zipfile.ZipInfo, limit: int) -> bytes:
    # O tamanho declarado no zip pode mentir, então o limite vale para os bytes lidos de fato.
    buffer = bytearray()
    with zf.open(info) as f:
        while chunk := f.read(64 * 1024):
            buffer.extend(chunk)
            if len(buffer) > limit:
                raise ZipRejected(f"O arquivo {info.filename} é grande demais. O limite é de {MAX_FILE_BYTES // 2**20} MB por arquivo.")
    return bytes(buffer)


def strip_common_root(files: dict[str, bytes]) -> dict[str, bytes]:
    tops = {path.split("/")[0] for path in files}
    if len(tops) == 1 and all("/" in path for path in files):
        root = tops.pop() + "/"
        return {path[len(root):]: data for path, data in files.items()}
    return files


def extract_zip(data: bytes) -> dict[str, bytes]:
    if len(data) > MAX_ZIP_BYTES:
        raise ZipRejected("O zip enviado é grande demais.")
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        raise ZipRejected("O arquivo enviado não é um zip válido. No Overleaf, use Menu > Download > Source.") from None

    files: dict[str, bytes] = {}
    total = 0
    with zf:
        entries = [i for i in zf.infolist() if not i.is_dir()]
        if len(entries) > MAX_FILES:
            raise ZipRejected(f"O zip tem mais de {MAX_FILES} arquivos.")
        for info in entries:
            path = safe_path(entry_name(info))
            if not path or is_ignored(path):
                continue
            content = read_limited(zf, info, MAX_FILE_BYTES)
            total += len(content)
            if total > MAX_TOTAL_BYTES:
                raise ZipRejected("O projeto descompactado passa do limite total de tamanho.")
            files[path] = content

    if not files:
        raise ZipRejected("O zip não tem nenhum arquivo do artigo.")
    return strip_common_root(files)


def looks_like_text(path: str, content: bytes) -> bool:
    suffix = PurePosixPath(path).suffix.lower()
    return suffix in TEXT_EXTENSIONS and b"\x00" not in content[:8000]


def decode_text(content: bytes) -> str:
    try:
        return content.decode("utf-8")
    except UnicodeDecodeError:
        return content.decode("latin-1")
