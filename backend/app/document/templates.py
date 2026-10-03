"""Modelos para começar um artigo novo.

Cada modelo é uma pasta em template_files/ com um projeto LaTeX completo, que também compila no Overleaf.
No main.tex, $titulo e $autor são trocados pelo título do artigo e pelo nome de quem o criou.
"""
from dataclasses import dataclass
from pathlib import Path
from string import Template as Fill

from app.document.texutils import escape

FILES_DIR = Path(__file__).parent / "template_files"


@dataclass(frozen=True)
class Template:
    id: str
    name: str
    description: str
    use_for: str
    language: str

    def build(self, title: str, author: str) -> dict[str, bytes]:
        files = {p.name: p.read_bytes() for p in sorted((FILES_DIR / self.id).iterdir()) if p.is_file()}
        main = Fill(files["main.tex"].decode("utf-8")).substitute(titulo=escape(title), autor=escape(author))
        files["main.tex"] = main.encode("utf-8")
        return files


TEMPLATES = [
    Template("sbc", "Artigo SBC", "Modelo da Sociedade Brasileira de Computação, com resumo em português e abstract em inglês.",
             "Congressos e workshops da SBC, como IHC, SBSI e WEI", "pt"),
    Template("abnt", "Artigo ABNT", "Margens e espaçamento da ABNT, citações por autor e ano e palavras-chave no resumo.",
             "Trabalhos de disciplina, revistas brasileiras e TCC em formato de artigo", "pt"),
    Template("ieee", "IEEE (conferência)", "Formato de conferência do IEEE, em inglês, com citações numeradas e palavras-chave.",
             "Conferências internacionais de computação e engenharia", "en"),
    Template("resumo-expandido", "Resumo expandido", "Texto curto, de 2 a 4 páginas, com objetivos e agradecimentos.",
             "Semanas acadêmicas, iniciação científica e eventos de extensão", "pt"),
    Template("em-branco", "Em branco", "Só o título, o resumo e a introdução, para montar do seu jeito.",
             "Quando nenhum dos outros serve", "pt"),
]
BY_ID = {t.id: t for t in TEMPLATES}
