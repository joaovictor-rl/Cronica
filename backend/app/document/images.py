import io
import threading
from pathlib import PurePosixPath

from PIL import Image

IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".pdf", ".gif")
_cache: dict[str, tuple[bytes, str]] = {}


def resolve_image(path: str, main_path: str, available) -> str | None:
    """Acha o arquivo de um \\includegraphics, que pode vir sem extensão ou relativo ao .tex principal."""
    folder = str(PurePosixPath(main_path).parent)
    bases = [path] if folder in ("", ".") else [f"{folder}/{path}", path]
    for base in bases:
        base = base.strip().lstrip("./")
        options = [base] if base.lower().endswith(IMAGE_EXTENSIONS) else [base + ext for ext in IMAGE_EXTENSIONS]
        for option in options:
            if option in available:
                return option
    return None


# O pdfium não aguenta duas threads ao mesmo tempo: sem esta trava, figuras em PDF pedidas em paralelo derrubam o servidor.
_pdfium_lock = threading.Lock()


def render_pdf_page(content: bytes, width: int, index: int = 0) -> Image.Image:
    """Desenha uma página de um PDF com a largura pedida, em pixels."""
    import pypdfium2

    with _pdfium_lock:
        pdf = pypdfium2.PdfDocument(content)
        try:
            page = pdf[index]
            image = page.render(scale=width / page.get_width()).to_pil()
            page.close()
        finally:
            pdf.close()
    return image


def pdf_page_count(content: bytes) -> int:
    import pypdfium2

    with _pdfium_lock:
        pdf = pypdfium2.PdfDocument(content)
        try:
            return len(pdf)
        finally:
            pdf.close()


def page_png(content: bytes, index: int, width: int) -> bytes:
    out = io.BytesIO()
    render_pdf_page(content, width, index).convert("RGB").save(out, "PNG", optimize=True)
    return out.getvalue()


def displayable(content: bytes, key: str, width: int = 1600) -> tuple[bytes, str]:
    """Devolve a imagem pronta para navegador e PDF; figuras em PDF viram PNG."""
    if key in _cache:
        return _cache[key]
    if content[:4] == b"%PDF":
        result = to_png(render_pdf_page(content, width)), "image/png"
    elif content[:8] == b"\x89PNG\r\n\x1a\n":
        result = content, "image/png"
    elif content[:3] == b"\xff\xd8\xff":
        result = content, "image/jpeg"
    else:
        result = to_png(Image.open(io.BytesIO(content))), "image/png"
    if len(_cache) > 64:
        _cache.clear()
    _cache[key] = result
    return result


def to_png(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.convert("RGB").save(buffer, "PNG", optimize=True)
    return buffer.getvalue()
