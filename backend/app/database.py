from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import DATABASE_URL

IS_SQLITE = DATABASE_URL.startswith("sqlite")

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    connect_args={"check_same_thread": False, "timeout": 30} if IS_SQLITE else {},
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

if IS_SQLITE:
    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, _):
        connection.execute("PRAGMA foreign_keys = ON")


class Base(DeclarativeBase):
    pass


def create_schema():
    """Cria as tabelas e acrescenta colunas novas em bancos de versões anteriores do Crônica."""
    import app.models as models  # registra as tabelas no Base antes de criar

    Base.metadata.create_all(engine)
    existing = inspect(engine)
    with engine.begin() as connection:
        for table in Base.metadata.sorted_tables:
            columns = {c["name"] for c in existing.get_columns(table.name)}
            for column in table.columns:
                if column.name in columns:
                    continue
                kind = column.type.compile(dialect=engine.dialect)
                if column.server_default is not None:
                    default = column.server_default.arg
                    connection.execute(text(f"ALTER TABLE {table.name} ADD COLUMN {column.name} {kind} NOT NULL DEFAULT '{default}'"))
                elif column.nullable:
                    connection.execute(text(f"ALTER TABLE {table.name} ADD COLUMN {column.name} {kind}"))

        # Versões antigas guardavam a versão atual numa tabela "branches"; agora ela fica no próprio artigo.
        if "branches" in existing.get_table_names():
            connection.execute(text(
                "UPDATE articles SET head_hash = (SELECT head_hash FROM branches"
                " WHERE branches.article_id = articles.id AND branches.name = 'main') WHERE head_hash IS NULL"
            ))
            connection.execute(text("DROP TABLE branches"))

        # Contas criadas antes dos códigos pessoais ganham um código agora.
        for (user_id,) in connection.execute(text("SELECT id FROM users WHERE code = ''")).all():
            connection.execute(text("UPDATE users SET code = :code WHERE id = :id"), {"code": models.new_code(), "id": user_id})
        connection.execute(text("DROP INDEX IF EXISTS ix_users_code"))
        connection.execute(text("CREATE UNIQUE INDEX ix_users_code ON users (code)"))


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
