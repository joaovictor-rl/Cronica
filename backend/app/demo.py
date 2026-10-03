"""Demonstração descartável.

Cada visitante que clica em "Entrar na demonstração" ganha uma cópia só sua: duas contas (a dele e a de
uma colega), o artigo real em quatro versões, uma organização e um convite esperando resposta. Nada do que
ele fizer aparece para outra pessoa, e tudo some quando a cópia expira ou o servidor reinicia.

Como os arquivos são guardados por conteúdo, as figuras do artigo ficam uma vez só no banco, por mais
cópias que existam: cada demonstração nova só acrescenta as versões e as árvores.
"""
import secrets
from datetime import timedelta
from functools import lru_cache
from pathlib import Path

from sqlalchemy import func, or_, select

from app import versioning
from app.accounts import collect_garbage, delete_users
from app.database import SessionLocal, create_schema
from app.document.blocks import graphics
from app.document.templates import BY_ID as TEMPLATES
from app.models import (
    Article,
    Invite,
    Organization,
    OrgMember,
    User,
    now,
)

PROJECT_DIR = Path(__file__).resolve().parents[2] / "examples" / "meu-sus-digital"
SANDBOX_HOURS = 3
MAX_SANDBOXES = 300
LEGACY_EMAILS = ("demo@cronica.dev", "colega@cronica.dev")  # contas fixas de versões anteriores
GROUP_NAME = "Grupo de IHC — UFPA (demonstração)"
DEMO_TITLE = "Usabilidade e Acessibilidade Digital para Idosos: Uma Avaliação do Aplicativo “Meu SUS Digital”"
ENDING = "\n\n\\bibliographystyle{sbc}\n\\bibliography{sbc-template}\n\n\\end{document}\n"


class DemoFull(Exception):
    """Muitas demonstrações abertas ao mesmo tempo."""


# Correções da última versão: erros de digitação, legendas repetidas e rótulos de figura duplicados.
REVISION = [
    ("\\maketitle\n\n9pp\n\\begin{abstractp}", "\\maketitle\n\n\\begin{abstract}"),
    ("informações informações", "informações"),
    ("a explicação a cerca das", "a explicação acerca das"),
    ("com o sistema.No contexto", "com o sistema. No contexto"),
    ("quantitativa).Dessa forma", "quantitativa). Dessa forma"),
    ("Meu SUS Digital,além", "Meu SUS Digital, além"),
    ("governamental,o Meu", "governamental, o Meu"),
    ("{barbosa2010ihc}.Por ser", "{barbosa2010ihc}. Por ser"),
    ("tarefa,a participante \\textit{}{P01}", "tarefa, a participante \\textit{P01}"),
    ("sobre ICM", "sobre IMC"),
    ("os usuário direcionassem", "os usuários direcionassem"),
    ("podendo se um fator", "podendo ser um fator"),
    ("das página de menu", "das páginas de menu"),
    ("inserção dos dados . Por fim", "inserção dos dados. Por fim"),
    ("avaliação heurística .", "avaliação heurística."),
    ("rótulo em negrito) , não há", "rótulo em negrito), não há"),
    ("Fluxo para exportar comprovante de vacinação.pdf}\n  \\caption{Redesign da tela de exportar comprovante de vacinação}\n  \\label{fig:signos-dinamicos}",
     "Fluxo para exportar comprovante de vacinação.pdf}\n  \\caption{Redesign da tela de exportar comprovante de vacinação}\n  \\label{fig:redesign-vacina}"),
    ("Fluxo para cadastrar IMC.pdf}\n  \\caption{Redesign da tela de exportar comprovante de vacinação}\n  \\label{fig:signos-dinamicos}",
     "Fluxo para cadastrar IMC.pdf}\n  \\caption{Redesign das telas de registro do IMC}\n  \\label{fig:redesign-imc}"),
    ("Fluxo para pesquisar no menu.pdf}\n  \\caption{Redesign da tela de exportar comprovante de vacinação}\n  \\label{fig:signos-dinamicos}",
     "Fluxo para pesquisar no menu.pdf}\n  \\caption{Redesign do menu com barra de pesquisa}\n  \\label{fig:redesign-menu}"),
    ("como visto na imagem 7b", "como visto na Figura~\\ref{fig:redesign-imc}b"),
    ("demonstrada na imagem 7d", "demonstrada na Figura~\\ref{fig:redesign-imc}d"),
    ("mostrado na imagem 7e", "mostrado na Figura~\\ref{fig:redesign-imc}e"),
]


def read_project() -> dict[str, bytes]:
    return {p.relative_to(PROJECT_DIR).as_posix(): p.read_bytes() for p in PROJECT_DIR.rglob("*") if p.is_file()}


def draft(files: dict[str, bytes], source: str, marker: str) -> dict[str, bytes]:
    """Uma versão anterior do artigo: o texto até `marker`, só com as imagens que ele usa."""
    cut = source.rfind("\n", 0, source.index(marker))
    text = source[:cut].rstrip() + ENDING
    used = {path.strip() for path in graphics(text)}
    kept = {p: c for p, c in files.items() if not p.startswith("imagens/") and p != "table.jpg"}
    kept.update({p: c for p, c in files.items() if p in used})
    kept["main.tex"] = text.encode()
    return kept


def revised(source: str) -> str:
    for old, new in REVISION:
        if source.count(old) != 1:
            raise ValueError(f"Trecho da revisão não encontrado: {old[:40]}")
        source = source.replace(old, new)
    return source


@lru_cache(maxsize=1)
def demo_steps() -> tuple:
    """As quatro versões do artigo, lidas do disco uma vez só."""
    files = read_project()
    source = files["main.tex"].decode("utf-8")
    return (
        (draft(files, source, "\\section{Resultados}"), "Introdução, fundamentação teórica e metodologia", 12, "voce"),
        (draft(files, source, "\\subsection{Aplicação do Método de Inspeção Semiótica"),
         "Resultados da avaliação heurística e do teste de usabilidade", 8, "colega"),
        (files, "Inspeção semiótica, redesign e considerações finais (versão enviada)", 4, "voce"),
        ({**files, "main.tex": revised(source).encode()},
         "Revisão: erros de digitação, legendas repetidas e rótulos das figuras", 1, "voce"),
    )


def demo_user(db, sandbox: str, slug: str, name: str, expires, **profile) -> User:
    user = User(
        name=name, email=f"{slug}-{sandbox}@demo.cronica", password_hash="!", sandbox=sandbox, expires_at=expires,
        institution="Universidade Federal do Pará (UFPA)", area="Interação Humano-Computador", **profile,
    )
    db.add(user)
    return user


def create_sandbox(db) -> User:
    """Cria a demonstração de um visitante e devolve a conta principal dela."""
    remove_expired(db)
    active = db.scalar(select(func.count()).select_from(User).where(User.sandbox.is_not(None)))
    if active >= MAX_SANDBOXES * 2:
        raise DemoFull
    sandbox = secrets.token_hex(8)
    expires = now() + timedelta(hours=SANDBOX_HOURS)
    user = demo_user(
        db, sandbox, "demo", "Conta de demonstração", expires, city="Belém, PA",
        status="Escrevendo sobre acessibilidade digital para idosos ✍",
        interests="Interação Humano-Computador\nAcessibilidade\nUsabilidade\nSaúde digital",
        bio=("Conta de exemplo do Crônica. O artigo dela foi escrito em grupo na disciplina de "
             "Interação Humano-Computador e importado do Overleaf. Mude o que quiser: esta cópia é só sua."),
    )
    colleague = demo_user(
        db, sandbox, "colega", "Colega de grupo", expires, city="Ananindeua, PA", theme="verde", pattern="bolinhas",
        status="Revisando os resultados do teste de usabilidade",
        interests="Avaliação heurística\nTeste de usabilidade",
        bio="Segunda conta de exemplo: escreveu os resultados do artigo e convidou a demonstração para um roteiro.",
    )
    db.commit()

    authors = {"voce": user, "colega": colleague}
    article = versioning.create_article(db, DEMO_TITLE, user)
    head = None
    for files, message, days_ago, author in demo_steps():
        version = versioning.commit(db, article, files, message, head, authors[author],
                                    created_at=now() - timedelta(days=days_ago))
        head = version.hash
    seed_group(db, user, colleague, article)
    return user


def seed_group(db, user: User, colleague: User, article: Article) -> None:
    """Uma organização com as duas contas e um convite esperando resposta, para mostrar a colaboração."""
    group = Organization(name=GROUP_NAME, owner_id=user.id, description=(
        "Grupo da disciplina de Interação Humano-Computador. Quem entra no grupo lê e edita os artigos dele."))
    db.add(group)
    db.flush()
    db.add_all([OrgMember(org_id=group.id, user_id=user.id), OrgMember(org_id=group.id, user_id=colleague.id)])
    article.org_id = group.id

    script = versioning.create_article(db, "Roteiro do teste de usabilidade com idosos", colleague)
    versioning.commit(db, script, TEMPLATES["abnt"].build(script.title, colleague.name), "Artigo criado a partir do modelo Artigo ABNT",
                      None, colleague, created_at=now() - timedelta(days=2))
    db.add(Invite(kind="artigo", target_id=script.id, from_id=colleague.id, to_id=user.id,
                  created_at=now() - timedelta(hours=5)))
    db.commit()


def other_account(db, user: User) -> User | None:
    """A outra conta da mesma demonstração, para ver o site pelos olhos da colega."""
    return db.scalar(select(User).where(User.sandbox == user.sandbox, User.id != user.id))


def remove_expired(db) -> None:
    expired = db.scalars(select(User.id).where(User.sandbox.is_not(None), User.expires_at < now())).all()
    delete_users(db, list(expired))


def reset_demo() -> None:
    """Ao subir o servidor: apaga todas as demonstrações (e as contas fixas antigas) e limpa o que sobrou."""
    create_schema()
    with SessionLocal() as db:
        ids = db.scalars(select(User.id).where(or_(User.sandbox.is_not(None), User.email.in_(LEGACY_EMAILS)))).all()
        delete_users(db, list(ids))
        collect_garbage(db)
