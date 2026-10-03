"""Fotos de perfil e de organização: qualquer imagem vira um JPEG quadrado e pequeno."""
import base64
import io
import re
import warnings

from fastapi import HTTPException, UploadFile, status
from PIL import Image, ImageOps

MAX_UPLOAD = 5 * 1024 * 1024
MAX_PIXELS = 40_000_000  # acima disso é mais provável um ataque do que uma foto
SIZE = 256


def process(content: bytes) -> bytes:
    """Valida, corrige a rotação do celular, recorta o centro e reduz para 256×256."""
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            image = Image.open(io.BytesIO(content))
            if image.width * image.height > MAX_PIXELS:
                raise ValueError("imagem grande demais")
            image.load()
    except (Image.DecompressionBombError, Image.DecompressionBombWarning, OSError, ValueError, SyntaxError):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Não consegui abrir a imagem. Envie um arquivo JPG, PNG, GIF ou WebP.")
    image = ImageOps.exif_transpose(image)
    if image.mode in ("RGBA", "LA", "P"):
        image = image.convert("RGBA")
        background = Image.new("RGB", image.size, "white")
        background.paste(image, mask=image.getchannel("A"))
        image = background
    image = ImageOps.fit(image.convert("RGB"), (SIZE, SIZE), Image.Resampling.LANCZOS)
    out = io.BytesIO()
    image.save(out, "JPEG", quality=85, optimize=True)  # salvar de novo também descarta metadados como GPS
    return out.getvalue()


async def read_upload(file: UploadFile) -> bytes:
    content = await file.read(MAX_UPLOAD + 1)
    if len(content) > MAX_UPLOAD:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "A imagem pode ter no máximo 5 MB.")
    return process(content)


FIGURE_MAX = 8 * 1024 * 1024
FIGURE_PATH = re.compile(r"imagens/[a-z0-9][a-z0-9._-]{0,80}\.(png|jpg)")


def figure(path: str, data: str) -> bytes:
    """Imagem nova de uma figura. PNG e JPEG ficam como vieram; outros formatos viram PNG, que o LaTeX aceita."""
    if not FIGURE_PATH.fullmatch(path):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Nome de imagem inválido.")
    try:
        content = base64.b64decode(data, validate=True)
    except ValueError:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Não consegui ler a imagem enviada.")
    if len(content) > FIGURE_MAX:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "Cada imagem pode ter no máximo 8 MB.")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            image = Image.open(io.BytesIO(content))
            if image.width * image.height > MAX_PIXELS:
                raise ValueError
            image.load()
    except (Image.DecompressionBombError, Image.DecompressionBombWarning, OSError, ValueError, SyntaxError):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Esse arquivo não é uma imagem que eu consiga abrir. Use PNG ou JPG.")
    wanted = "PNG" if path.endswith(".png") else "JPEG"
    if image.format == wanted:
        return content
    out = io.BytesIO()
    if wanted == "JPEG":
        image = image.convert("RGB")
    image.save(out, wanted)
    return out.getvalue()
