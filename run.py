"""Roda o Crônica no seu computador com um único comando: python run.py"""
import os
import subprocess
import sys
import threading
import webbrowser
from pathlib import Path

BACKEND = Path(__file__).resolve().parent / "backend"
URL = "http://localhost:8000"


def ready() -> bool:
    try:
        import app.main  # noqa: F401  (se faltar alguma dependência, o import falha)
        return True
    except ImportError:
        return False


def main():
    if sys.version_info < (3, 11):
        sys.exit("O Crônica precisa do Python 3.11 ou mais novo. Baixe em https://www.python.org/downloads/")
    sys.path.insert(0, str(BACKEND))
    if not ready():
        if os.environ.get("CRONICA_RESTARTED"):
            sys.exit("Instalei as dependências, mas o Python não conseguiu carregá-las. Rode: python -m pip install -r backend/requirements.txt")
        print("Instalando as dependências (só na primeira vez)...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "--disable-pip-version-check", "--no-warn-script-location",
                               "-r", str(BACKEND / "requirements.txt")])
        # O Python só enxerga pacotes recém-instalados numa execução nova, então o script se reinicia.
        try:
            sys.exit(subprocess.call([sys.executable, *sys.argv], env={**os.environ, "CRONICA_RESTARTED": "1"}))
        except KeyboardInterrupt:
            sys.exit(0)

    import uvicorn
    print(f"\nCrônica rodando em {URL}")
    print('Para conhecer, clique em "Entrar na demonstração". Para parar, aperte Ctrl+C.\n')
    threading.Timer(1.5, lambda: webbrowser.open(URL)).start()
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000)


if __name__ == "__main__":
    main()
