"""Regressões leves de acessibilidade para o painel remoto.

Os comportamentos reais de foco e viewport são cobertos pelo roteiro Playwright
registrado no vault; estes checks são rápidos e independem de navegador.
"""

from html.parser import HTMLParser
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
HTML = (RAIZ / "src" / "remote_panel.html").read_text(encoding="utf-8")
JS = (RAIZ / "src" / "remote_panel.js").read_text(encoding="utf-8")
CSS = (RAIZ / "src" / "remote_panel.css").read_text(encoding="utf-8")


class _Tags(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags: list[tuple[str, dict[str, str | None]]] = []

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))


def _elementos():
    parser = _Tags()
    parser.feed(HTML)
    return parser.tags


def test_abas_e_paineis_estao_associados():
    tags = _elementos()
    abas = [a for tag, a in tags if tag == "button" and a.get("role") == "tab"]
    paineis = [a for tag, a in tags if tag == "section" and a.get("role") == "tabpanel"]
    assert len(abas) == len(paineis) == 4
    assert sum(a["aria-selected"] == "true" for a in abas) == 1
    assert {a["id"] for a in abas} == {p["aria-labelledby"] for p in paineis}
    assert {a["aria-controls"] for a in abas} == {p["id"] for p in paineis}
    assert all(a["tabindex"] == "-1" for a in abas if a["aria-selected"] == "false")


def test_navegacao_por_teclado_e_estado_acessivel():
    assert "e.key === 'ArrowRight'" in JS
    assert "e.key === 'ArrowLeft'" in JS
    assert "e.key === 'Home'" in JS
    assert "e.key === 'End'" in JS
    assert "setAttribute('aria-selected'" in JS
    assert "t.tabIndex = ativa ? 0 : -1" in JS


def test_foco_mensagem_feedback_e_tema():
    tags = _elementos()
    entrada = next(a for _, a in tags if a.get("id") == "entrada")
    aviso = next(a for _, a in tags if a.get("id") == "toast")
    assert entrada["aria-label"] == "Mensagem ao DeepSeek"
    assert aviso["aria-live"] == "polite"
    assert aviso["aria-atomic"] == "true"
    assert "role', erro ? 'alert' : 'status'" in JS
    assert "/remote_panel.css?v=10" in HTML
    assert "/remote_panel.js?v=10" in HTML


def test_layout_inclusivo_e_respeito_ao_movimento():
    assert 'nav.tabs .tab:focus-visible' in CSS
    assert 'min-height: 44px;' in CSS
    assert '@media (max-width: 550px)' in CSS
    assert '@media (min-width: 900px)' in CSS
    assert 'prefers-reduced-motion: reduce' in CSS
