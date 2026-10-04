"""Configurações que mudam de um lugar para outro (no seu computador ou na hospedagem), lidas de variáveis de ambiente."""
import os
import re
import secrets
from pathlib import Path

# Sem DATABASE_URL, o banco é um arquivo SQLite na pasta backend: nada para instalar.
# Na hospedagem os arquivos do servidor são apagados a cada reinício: lá o banco precisa ser externo.
if os.getenv("RENDER") and not os.getenv("DATABASE_URL"):
    raise SystemExit("Falta a variável DATABASE_URL com o endereço do banco (Neon). Configure em Environment, no Render.")
DATABASE_URL = os.getenv("DATABASE_URL") or "sqlite:///" + (Path(__file__).resolve().parent.parent / "cronica.db").as_posix()
# Serviços como Neon e Render entregam "postgresql://..." ou "postgres://..."; o Crônica usa o driver psycopg 3.
DATABASE_URL = re.sub(r"^postgres(ql)?://", "postgresql+psycopg://", DATABASE_URL)

# Chave que assina os logins. Na hospedagem, defina JWT_SECRET; sem ela, cada vez que o servidor
# reinicia é gerada uma chave nova e todo mundo precisa entrar de novo (seguro, mas inconveniente).
JWT_SECRET = os.getenv("JWT_SECRET") or secrets.token_urlsafe(32)
JWT_EXPIRES_MINUTES = int(os.getenv("JWT_EXPIRES_MINUTES", "720"))
