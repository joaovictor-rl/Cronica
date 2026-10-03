from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles

from app.demo import reset_demo
from app.routers import articles, auth, orgs, people, references, templates, versions

STATIC_DIR = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    reset_demo()  # cria as tabelas que faltam e apaga as demonstrações da última vez
    yield


app = FastAPI(title="Crônica API", description="Versões, comparação e escrita em grupo de artigos acadêmicos.", lifespan=lifespan)
for module in (auth, articles, versions, people, orgs, templates, references):
    app.include_router(module.router)

# O site só carrega scripts, estilos e imagens dele mesmo, e não pode ser aberto dentro de outro site.
# A página /docs (documentação da API) usa scripts de fora, então fica sem essa regra.
CSP = ("default-src 'self'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; "
       "script-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "same-origin"
    if not request.url.path.startswith(("/docs", "/redoc", "/openapi.json")):
        response.headers["Content-Security-Policy"] = CSP
    return response


@app.get("/health", tags=["saúde"])
def health():
    return {"status": "ok"}


# A interface vem por último: as rotas da API acima têm prioridade sobre os arquivos estáticos.
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="interface")
