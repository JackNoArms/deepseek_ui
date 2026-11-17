"""Temas, tokens de cor e a folha QSS (o "CSS do Qt") da janela.

Seis temas trocáveis em tempo real (`TEMAS`), todos com os mesmos nomes de
token. `aplicar_tema(nome)` copia a paleta para `Color`; quem desenha lê
`Color.X` na hora, e o QSS é regerado por `stylesheet()`. O painel do
celular recebe as mesmas paletas por `css_temas_remotos()`.

Semântica fixa de cor, igual em todos os temas:

- **ACCENT**: ação principal, foco, seleção, pergunta pendente.
- **DEEPTHINK** (violeta): só o DeepThink.
- **RECOMMEND** (âmbar): o que o DeepSeek recomenda numa decisão.
- **SUCCESS** (verde): o que você escolheu / deu certo.
- **DANGER** (vermelho): destrutivo, erro, cancelar fila.

`BW` é a espessura de borda: 2px nos temas de alto contraste.
"""

_GRAFITE = {
    "BG": "#0F1115", "SURFACE": "#15181E", "SURFACE_ALT": "#1A1E26",
    "SURFACE_HIGH": "#212632", "SURFACE_PRESSED": "#2A3040",
    "CODE_BG": "#0B0D11", "CODE_TEXT": "#D5DBE6", "CODE_INLINE": "#A9BCFF",
    "BORDER": "#272C38", "BORDER_SOFT": "#1D212A", "BORDER_STRONG": "#353C4C",
    "TEXT": "#E7EAF0", "TEXT_DIM": "#9BA3B4", "TEXT_MUTED": "#646C7C",
    "ACCENT": "#5B7CFA", "ACCENT_HOVER": "#7B96FF", "ACCENT_PRESSED": "#4562DB",
    "ACCENT_SOFT": "#1A2240", "ACCENT_SOFT_HOVER": "#212B50",
    "ON_ACCENT": "#FFFFFF", "SELECTION": "#2B3A6B",
    "SUCCESS": "#3CC48E", "SUCCESS_HOVER": "#52D3A0", "SUCCESS_PRESSED": "#2C9A6E",
    "SUCCESS_SOFT": "#11261D", "SUCCESS_LINE": "#1C3D2F", "ON_SUCCESS": "#06140E",
    "DANGER": "#F0575D", "DANGER_HOVER": "#F36F74", "DANGER_PRESSED": "#C24046",
    "DANGER_SOFT": "#2A1518", "ON_DANGER": "#FFFFFF",
    "WARNING": "#F2B84B",
    "RECOMMEND": "#F2B84B", "RECOMMEND_SOFT": "#2A2214", "RECOMMEND_HOVER": "#352A16",
    "RECOMMEND_LINE": "#4A3B1C", "RECOMMEND_TEXT": "#F5D79A",
    "RECOMMEND_FADED": "#9C8558", "RECOMMEND_FADED_LINE": "#6B5A33",
    "DEEPTHINK": "#A78BFA", "DEEPTHINK_PRESSED": "#8B6FE0", "SEARCH": "#38BDF8",
    "USER_BUBBLE": "#1B2340", "USER_BORDER": "#2B3765",
    "DIFF_ADD_BG": "#0F2A1E", "DIFF_ADD_FG": "#6FE0A8",
    "DIFF_DEL_BG": "#2C1418", "DIFF_DEL_FG": "#FF8A8F",
    "BW": "1px",
}

_OCEANO = {
    "BG": "#0A1220", "SURFACE": "#0F1A2D", "SURFACE_ALT": "#13213A",
    "SURFACE_HIGH": "#1A2B49", "SURFACE_PRESSED": "#22375C",
    "CODE_BG": "#081020", "CODE_TEXT": "#D3E2F5", "CODE_INLINE": "#7FE3F7",
    "BORDER": "#20335A", "BORDER_SOFT": "#182844", "BORDER_STRONG": "#2C4573",
    "TEXT": "#E6EEF9", "TEXT_DIM": "#93A6C4", "TEXT_MUTED": "#5D7193",
    "ACCENT": "#22C3E6", "ACCENT_HOVER": "#4FD5F0", "ACCENT_PRESSED": "#159CBA",
    "ACCENT_SOFT": "#0D2C3D", "ACCENT_SOFT_HOVER": "#12394F",
    "ON_ACCENT": "#04121A", "SELECTION": "#1C4A66",
    "SUCCESS": "#4ADE80", "SUCCESS_HOVER": "#6EE89A", "SUCCESS_PRESSED": "#2FB862",
    "SUCCESS_SOFT": "#0E2A1C", "SUCCESS_LINE": "#1A4A30", "ON_SUCCESS": "#052012",
    "DANGER": "#FB7185", "DANGER_HOVER": "#FC8C9C", "DANGER_PRESSED": "#D9566B",
    "DANGER_SOFT": "#2D1520", "ON_DANGER": "#FFFFFF",
    "WARNING": "#FBBF24",
    "RECOMMEND": "#FBBF24", "RECOMMEND_SOFT": "#2B2410", "RECOMMEND_HOVER": "#382F14",
    "RECOMMEND_LINE": "#4D3F17", "RECOMMEND_TEXT": "#FDE3A0",
    "RECOMMEND_FADED": "#A08A55", "RECOMMEND_FADED_LINE": "#6B5B2E",
    "DEEPTHINK": "#C4B5FD", "DEEPTHINK_PRESSED": "#A594E8", "SEARCH": "#38BDF8",
    "USER_BUBBLE": "#123049", "USER_BORDER": "#1E4C6E",
    "DIFF_ADD_BG": "#0C2A1E", "DIFF_ADD_FG": "#6FE0A8",
    "DIFF_DEL_BG": "#2D1520", "DIFF_DEL_FG": "#FF8A9A",
    "BW": "1px",
}

_PAPEL = {
    "BG": "#F5F6F8", "SURFACE": "#FFFFFF", "SURFACE_ALT": "#F9FAFB",
    "SURFACE_HIGH": "#EEF0F4", "SURFACE_PRESSED": "#E3E7EE",
    "CODE_BG": "#F3F4F7", "CODE_TEXT": "#2A3140", "CODE_INLINE": "#3349CC",
    "BORDER": "#E1E4EA", "BORDER_SOFT": "#ECEEF2", "BORDER_STRONG": "#C9CED8",
    "TEXT": "#1A1D24", "TEXT_DIM": "#5B6272", "TEXT_MUTED": "#8C93A1",
    "ACCENT": "#4D6BFE", "ACCENT_HOVER": "#3F5CF0", "ACCENT_PRESSED": "#3349CC",
    "ACCENT_SOFT": "#EBEFFF", "ACCENT_SOFT_HOVER": "#DDE4FF",
    "ON_ACCENT": "#FFFFFF", "SELECTION": "#C9D3FF",
    "SUCCESS": "#16884A", "SUCCESS_HOVER": "#12753F", "SUCCESS_PRESSED": "#0E5F33",
    "SUCCESS_SOFT": "#E7F6EE", "SUCCESS_LINE": "#B6E2C8", "ON_SUCCESS": "#FFFFFF",
    "DANGER": "#D63B43", "DANGER_HOVER": "#C2323A", "DANGER_PRESSED": "#B02E35",
    "DANGER_SOFT": "#FDECEE", "ON_DANGER": "#FFFFFF",
    "WARNING": "#B56A00",
    "RECOMMEND": "#C27A0E", "RECOMMEND_SOFT": "#FFF5E0", "RECOMMEND_HOVER": "#FFEDC7",
    "RECOMMEND_LINE": "#F0D39A", "RECOMMEND_TEXT": "#7A4B05",
    "RECOMMEND_FADED": "#A88850", "RECOMMEND_FADED_LINE": "#E2C891",
    "DEEPTHINK": "#7C5CE0", "DEEPTHINK_PRESSED": "#6446C4", "SEARCH": "#0E8BC2",
    "USER_BUBBLE": "#EBEFFF", "USER_BORDER": "#CBD5FF",
    "DIFF_ADD_BG": "#E6F6EC", "DIFF_ADD_FG": "#116B3A",
    "DIFF_DEL_BG": "#FDECEE", "DIFF_DEL_FG": "#B42330",
    "BW": "1px",
}

_ESCURO = {
    "BG": "#000000", "SURFACE": "#0C0C0E", "SURFACE_ALT": "#121215",
    "SURFACE_HIGH": "#1B1B20", "SURFACE_PRESSED": "#25252B",
    "CODE_BG": "#050506", "CODE_TEXT": "#DCDCE0", "CODE_INLINE": "#9DB0FF",
    "BORDER": "#26262C", "BORDER_SOFT": "#18181C", "BORDER_STRONG": "#34343C",
    "TEXT": "#ECECEF", "TEXT_DIM": "#A1A1AA", "TEXT_MUTED": "#6B6B74",
    "ACCENT": "#4D6BFE", "ACCENT_HOVER": "#6C86FF", "ACCENT_PRESSED": "#3A55DB",
    "ACCENT_SOFT": "#141A3A", "ACCENT_SOFT_HOVER": "#1B2350",
    "ON_ACCENT": "#FFFFFF", "SELECTION": "#26346E",
    "SUCCESS": "#34C77B", "SUCCESS_HOVER": "#4FD690", "SUCCESS_PRESSED": "#279E61",
    "SUCCESS_SOFT": "#0B2016", "SUCCESS_LINE": "#17402A", "ON_SUCCESS": "#04140B",
    "DANGER": "#F2555A", "DANGER_HOVER": "#F56E72", "DANGER_PRESSED": "#C53F44",
    "DANGER_SOFT": "#26100F", "ON_DANGER": "#FFFFFF",
    "WARNING": "#F5B841",
    "RECOMMEND": "#F5B841", "RECOMMEND_SOFT": "#231C0B", "RECOMMEND_HOVER": "#2E2510",
    "RECOMMEND_LINE": "#463815", "RECOMMEND_TEXT": "#F7D892",
    "RECOMMEND_FADED": "#988257", "RECOMMEND_FADED_LINE": "#64552F",
    "DEEPTHINK": "#A78BFA", "DEEPTHINK_PRESSED": "#8B6FE0", "SEARCH": "#38BDF8",
    "USER_BUBBLE": "#141A3A", "USER_BORDER": "#28336E",
    "DIFF_ADD_BG": "#0B2016", "DIFF_ADD_FG": "#6FE0A8",
    "DIFF_DEL_BG": "#26100F", "DIFF_DEL_FG": "#FF8A8F",
    "BW": "1px",
}

_ALTO_CONTRASTE_ESCURO = {
    "BG": "#000000", "SURFACE": "#000000", "SURFACE_ALT": "#0A0A0A",
    "SURFACE_HIGH": "#1A1A1A", "SURFACE_PRESSED": "#2A2A2A",
    "CODE_BG": "#000000", "CODE_TEXT": "#FFFFFF", "CODE_INLINE": "#8FE6FF",
    "BORDER": "#9A9A9A", "BORDER_SOFT": "#5C5C5C", "BORDER_STRONG": "#FFFFFF",
    "TEXT": "#FFFFFF", "TEXT_DIM": "#E6E6E6", "TEXT_MUTED": "#C2C2C2",
    "ACCENT": "#3FD0FF", "ACCENT_HOVER": "#7FE0FF", "ACCENT_PRESSED": "#1FB0E0",
    "ACCENT_SOFT": "#00222E", "ACCENT_SOFT_HOVER": "#003344",
    "ON_ACCENT": "#000000", "SELECTION": "#005A80",
    "SUCCESS": "#5CFF8F", "SUCCESS_HOVER": "#8CFFB0", "SUCCESS_PRESSED": "#2EE06A",
    "SUCCESS_SOFT": "#00290F", "SUCCESS_LINE": "#5CFF8F", "ON_SUCCESS": "#000000",
    "DANGER": "#FF6B6B", "DANGER_HOVER": "#FF9090", "DANGER_PRESSED": "#E04848",
    "DANGER_SOFT": "#330000", "ON_DANGER": "#000000",
    "WARNING": "#FFD23F",
    "RECOMMEND": "#FFD23F", "RECOMMEND_SOFT": "#2B2300", "RECOMMEND_HOVER": "#3D3200",
    "RECOMMEND_LINE": "#FFD23F", "RECOMMEND_TEXT": "#FFE58A",
    "RECOMMEND_FADED": "#E0C060", "RECOMMEND_FADED_LINE": "#B89A30",
    "DEEPTHINK": "#D0B3FF", "DEEPTHINK_PRESSED": "#B590FF", "SEARCH": "#3FD0FF",
    "USER_BUBBLE": "#001B33", "USER_BORDER": "#3FD0FF",
    "DIFF_ADD_BG": "#00290F", "DIFF_ADD_FG": "#8CFFB0",
    "DIFF_DEL_BG": "#330000", "DIFF_DEL_FG": "#FF9C9C",
    "BW": "2px",
}

_ALTO_CONTRASTE_CLARO = {
    "BG": "#FFFFFF", "SURFACE": "#FFFFFF", "SURFACE_ALT": "#F2F2F2",
    "SURFACE_HIGH": "#E6E6E6", "SURFACE_PRESSED": "#D4D4D4",
    "CODE_BG": "#F5F5F5", "CODE_TEXT": "#000000", "CODE_INLINE": "#0030B8",
    "BORDER": "#595959", "BORDER_SOFT": "#8C8C8C", "BORDER_STRONG": "#000000",
    "TEXT": "#000000", "TEXT_DIM": "#1F1F1F", "TEXT_MUTED": "#3D3D3D",
    "ACCENT": "#0037DA", "ACCENT_HOVER": "#002BB0", "ACCENT_PRESSED": "#00208A",
    "ACCENT_SOFT": "#E5ECFF", "ACCENT_SOFT_HOVER": "#D2DDFF",
    "ON_ACCENT": "#FFFFFF", "SELECTION": "#9DB7FF",
    "SUCCESS": "#006B2E", "SUCCESS_HOVER": "#005724", "SUCCESS_PRESSED": "#00441C",
    "SUCCESS_SOFT": "#E3F7EA", "SUCCESS_LINE": "#006B2E", "ON_SUCCESS": "#FFFFFF",
    "DANGER": "#B00020", "DANGER_HOVER": "#8E001A", "DANGER_PRESSED": "#700014",
    "DANGER_SOFT": "#FDE7EA", "ON_DANGER": "#FFFFFF",
    "WARNING": "#8A4B00",
    "RECOMMEND": "#8A4B00", "RECOMMEND_SOFT": "#FFF0D1", "RECOMMEND_HOVER": "#FFE4AD",
    "RECOMMEND_LINE": "#8A4B00", "RECOMMEND_TEXT": "#5C3200",
    "RECOMMEND_FADED": "#6E4A1A", "RECOMMEND_FADED_LINE": "#8A6A3A",
    "DEEPTHINK": "#5B2BC9", "DEEPTHINK_PRESSED": "#4720A0", "SEARCH": "#005C8A",
    "USER_BUBBLE": "#E5ECFF", "USER_BORDER": "#0037DA",
    "DIFF_ADD_BG": "#E3F7EA", "DIFF_ADD_FG": "#004D21",
    "DIFF_DEL_BG": "#FDE7EA", "DIFF_DEL_FG": "#8E001A",
    "BW": "2px",
}

# Ordem = ordem do menu. `escuro` decide o `color-scheme` no celular.
TEMAS = {
    "grafite": {"rotulo": "Grafite Índigo", "escuro": True, "cores": _GRAFITE},
    "oceano": {"rotulo": "Oceano Profundo", "escuro": True, "cores": _OCEANO},
    "papel": {"rotulo": "Claro Papel", "escuro": False, "cores": _PAPEL},
    "escuro": {"rotulo": "Escuro", "escuro": True, "cores": _ESCURO},
    "alto_contraste_escuro": {"rotulo": "Alto contraste escuro", "escuro": True,
                              "cores": _ALTO_CONTRASTE_ESCURO},
    "alto_contraste_claro": {"rotulo": "Alto contraste claro", "escuro": False,
                             "cores": _ALTO_CONTRASTE_CLARO},
}
TEMA_PADRAO = "grafite"


class Color:
    """Tokens do tema ativo. Valores trocados por `aplicar_tema`."""

    NOME = TEMA_PADRAO
    ESCURO = True


MONO = "JetBrains Mono, Cascadia Mono, Consolas, monospace"
SANS = "Segoe UI Variable Text, Segoe UI, sans-serif"

TONE: dict[str, str] = {}


def aplicar_tema(nome: str | None) -> str:
    """Torna `nome` o tema ativo e devolve o nome efetivo (padrão se inválido)."""
    if nome not in TEMAS:
        nome = TEMA_PADRAO
    tema = TEMAS[nome]
    for chave, valor in tema["cores"].items():
        setattr(Color, chave, valor)
    Color.NOME = nome
    Color.ESCURO = tema["escuro"]
    TONE.clear()
    TONE.update({
        "success": Color.SUCCESS,
        "danger": Color.DANGER,
        "accent": Color.ACCENT,
        "muted": Color.TEXT_DIM,
    })
    return nome


aplicar_tema(TEMA_PADRAO)


def tema_atual() -> str:
    return Color.NOME


def soft(hexcolor: str) -> str:
    """Cor misturada ao fundo (16%), para preencher chips ligados."""
    base = Color.SURFACE

    def canais(h):
        return [int(h[i:i + 2], 16) for i in (1, 3, 5)]

    misturado = [round(c * 0.16 + b * 0.84)
                 for c, b in zip(canais(hexcolor), canais(base))]
    return "#" + "".join(f"{v:02x}" for v in misturado)


# Token do Qt → variável CSS do painel do celular.
_CSS_VARS = {
    "BG": "--bg", "SURFACE": "--surface", "SURFACE_ALT": "--surface-alt",
    "SURFACE_HIGH": "--surface-high", "SURFACE_PRESSED": "--surface-pressed",
    "CODE_BG": "--code-bg", "BORDER": "--border", "BORDER_SOFT": "--border-soft",
    "BORDER_STRONG": "--border-strong", "TEXT": "--text", "TEXT_DIM": "--text-dim",
    "TEXT_MUTED": "--text-muted", "ACCENT": "--accent",
    "ACCENT_HOVER": "--accent-hover", "ACCENT_PRESSED": "--accent-pressed",
    "ACCENT_SOFT": "--accent-soft", "ON_ACCENT": "--on-accent",
    "SUCCESS": "--success", "SUCCESS_PRESSED": "--success-pressed",
    "SUCCESS_SOFT": "--success-soft", "SUCCESS_LINE": "--success-line",
    "DANGER": "--danger", "DANGER_HOVER": "--danger-hover",
    "DANGER_PRESSED": "--danger-pressed", "DANGER_SOFT": "--danger-soft",
    "ON_DANGER": "--on-danger",
    "RECOMMEND": "--recommend", "RECOMMEND_SOFT": "--recommend-soft",
    "RECOMMEND_TEXT": "--recommend-text", "RECOMMEND_LINE": "--recommend-line",
    "RECOMMEND_FADED": "--recommend-faded",
    "RECOMMEND_FADED_LINE": "--recommend-faded-line",
    "DEEPTHINK": "--deepthink", "DEEPTHINK_PRESSED": "--deepthink-pressed",
    "USER_BUBBLE": "--user-bubble", "USER_BORDER": "--user-border",
    "SELECTION": "--selection", "BW": "--bw",
}


def css_temas_remotos() -> str:
    """As seis paletas como CSS para o painel do celular.

    `:root` recebe o tema padrão; cada tema vira `:root[data-tema="<nome>"]`.
    Fonte única: as mesmas tabelas que pintam o app no PC.
    """
    blocos = []
    for nome, tema in TEMAS.items():
        linhas = [f"  {var}: {tema['cores'][chave]};"
                  for chave, var in _CSS_VARS.items()]
        linhas.append(f"  color-scheme: {'dark' if tema['escuro'] else 'light'};")
        corpo = "\n".join(linhas)
        seletor = f':root[data-tema="{nome}"]'
        if nome == TEMA_PADRAO:
            seletor = ":root, " + seletor
        blocos.append(f"{seletor} {{\n{corpo}\n}}")
    return "\n".join(blocos) + "\n"


def stylesheet() -> str:
    c = Color
    return f"""
* {{ font-family: {SANS}; color: {c.TEXT}; outline: none; }}

QMainWindow, QWidget#root {{ background: {c.BG}; }}

QToolTip {{
    background: {c.SURFACE_HIGH};
    color: {c.TEXT};
    border: {c.BW} solid {c.BORDER_STRONG};
    border-radius: 6px;
    padding: 6px 8px;
}}

/* ---------- Cabeçalho ---------- */
QFrame#header {{ background: {c.SURFACE}; border-bottom: {c.BW} solid {c.BORDER}; }}
QLabel#brand {{ font-size: 15px; font-weight: 700; letter-spacing: 0.2px; }}
QLabel#brandMark {{ color: {c.ACCENT}; font-size: 18px; font-weight: 800; }}
QLabel#status {{ font-size: 11px; color: {c.TEXT_DIM}; }}
QFrame#headerSep {{ background: {c.BORDER}; border: none; }}

/* ---------- Botões em geral ---------- */
QPushButton {{
    background: {c.SURFACE_ALT};
    border: {c.BW} solid {c.BORDER};
    border-radius: 8px;
    padding: 6px 12px;
    font-size: 12px;
    font-weight: 600;
}}
QPushButton:hover {{ background: {c.SURFACE_HIGH}; border-color: {c.BORDER_STRONG}; }}
QPushButton:pressed {{ background: {c.SURFACE_PRESSED}; border-color: {c.ACCENT}; }}
QPushButton:disabled {{ color: {c.TEXT_MUTED}; background: {c.SURFACE}; border-color: {c.BORDER_SOFT}; }}
QPushButton:checked {{ background: {c.ACCENT_SOFT}; border-color: {c.ACCENT}; color: {c.TEXT}; }}

QPushButton#danger {{ color: {c.DANGER}; }}
QPushButton#danger:hover {{
    background: {c.DANGER_SOFT};
    border-color: {c.DANGER};
    color: {c.DANGER};
}}
QPushButton#danger:pressed {{
    background: {c.SURFACE_PRESSED};
    border-color: {c.DANGER};
    color: {c.DANGER_PRESSED};
}}
QPushButton#danger:disabled {{
    color: {c.TEXT_MUTED};
    background: {c.SURFACE};
    border-color: {c.BORDER_SOFT};
}}

QLabel#project {{ font-size: 12px; color: {c.TEXT_DIM}; font-weight: 600; }}
QLabel#fieldLabel {{
    color: {c.TEXT_DIM};
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.6px;
}}
QLabel#fieldHelp {{
    color: {c.TEXT_MUTED};
    font-size: 11px;
}}

/* Botões de ferramenta do cabeçalho: fantasmas, ganham corpo no hover. */
QPushButton#openFolder {{
    background: transparent;
    border: {c.BW} solid transparent;
    color: {c.TEXT_DIM};
    padding: 6px 10px;
}}
QPushButton#openFolder:hover {{
    background: {c.SURFACE_HIGH};
    border-color: {c.BORDER};
    color: {c.TEXT};
}}
QPushButton#openFolder:pressed {{ background: {c.SURFACE_PRESSED}; border-color: {c.ACCENT}; }}
QPushButton#openFolder:checked {{
    background: {c.ACCENT_SOFT};
    border-color: {c.ACCENT};
    color: {c.TEXT};
}}
QPushButton#openFolder:disabled {{ color: {c.TEXT_MUTED}; background: transparent; border-color: transparent; }}
QPushButton#connect {{ background: {c.SUCCESS}; border: none; color: {c.ON_SUCCESS}; padding: 7px 14px; }}
QPushButton#connect:hover {{ background: {c.SUCCESS_HOVER}; }}
QPushButton#connect:pressed {{ background: {c.SUCCESS_PRESSED}; color: {c.ON_SUCCESS}; }}
QPushButton#connectOn {{ background: {c.DANGER_SOFT}; border: {c.BW} solid {c.DANGER}; color: {c.DANGER}; padding: 7px 14px; }}
QPushButton#connectOn:hover {{ background: {c.DANGER}; color: {c.ON_DANGER}; }}
QPushButton#connectOn:pressed {{ background: {c.DANGER_PRESSED}; color: {c.ON_DANGER}; }}

QScrollArea, QScrollArea > QWidget > QWidget {{ background: {c.BG}; border: none; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {c.BORDER}; border-radius: 3px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: {c.BORDER_STRONG}; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: {c.BORDER}; border-radius: 3px; min-width: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

/* Botão flutuante "Ir para o fim" (sobre o chat). */
QToolButton#scrollToEnd {{
    background: {c.SURFACE_HIGH};
    border: {c.BW} solid {c.BORDER_STRONG};
    border-radius: 15px;
    color: {c.TEXT};
    padding: 6px 14px;
    font-size: 12px;
    font-weight: 600;
}}
QToolButton#scrollToEnd:hover {{ border-color: {c.ACCENT}; background: {c.SURFACE_PRESSED}; }}
QToolButton#scrollToEnd[novidade="true"] {{
    background: {c.ACCENT};
    border-color: {c.ACCENT};
    color: {c.ON_ACCENT};
}}
QToolButton#scrollToEnd[novidade="true"]:hover {{ background: {c.ACCENT_HOVER}; }}

/* ---------- Mensagens ---------- */
QFrame#userBubble {{
    background: {c.USER_BUBBLE};
    border: {c.BW} solid {c.USER_BORDER};
    border-radius: 14px;
    border-bottom-right-radius: 4px;
}}
QLabel#userText {{ font-size: 13px; }}
QLabel#agentText {{ font-size: 13px; color: {c.TEXT}; }}
QLabel#agentGlyph {{
    color: {c.ACCENT};
    background: {c.ACCENT_SOFT};
    border: {c.BW} solid {c.USER_BORDER};
    border-radius: 11px;
    font-size: 11px;
    font-weight: 800;
}}

QFrame#codeCard {{
    background: {c.CODE_BG};
    border: {c.BW} solid {c.BORDER};
    border-radius: 10px;
}}
QFrame#codeHeader {{
    background: {c.SURFACE};
    border-bottom: {c.BW} solid {c.BORDER};
    border-top-left-radius: 10px;
    border-top-right-radius: 10px;
}}
QLabel#codeLang {{
    font-family: {MONO};
    font-size: 10px;
    font-weight: 700;
    color: {c.TEXT_DIM};
    letter-spacing: 1px;
}}
QToolButton#codeAction {{
    background: transparent;
    border: {c.BW} solid {c.BORDER};
    border-radius: 6px;
    color: {c.TEXT_DIM};
    padding: 3px 9px;
    font-size: 11px;
}}
QToolButton#codeAction:hover {{ color: {c.TEXT}; border-color: {c.ACCENT}; }}
QToolButton#codeAction:pressed {{ background: {c.SURFACE_PRESSED}; color: {c.TEXT}; }}
QPlainTextEdit#codeBody {{
    background: transparent;
    border: none;
    font-family: {MONO};
    font-size: 12px;
    color: {c.CODE_TEXT};
}}

/* ---------- Campos de texto ---------- */
QLineEdit {{
    background: {c.SURFACE_ALT};
    border: {c.BW} solid {c.BORDER};
    border-radius: 8px;
    color: {c.TEXT};
    padding: 7px 10px;
    selection-background-color: {c.SELECTION};
    selection-color: {c.TEXT};
    font-size: 13px;
}}
QLineEdit:focus {{ border-color: {c.ACCENT}; }}
QLineEdit:disabled {{
    background: {c.SURFACE};
    color: {c.TEXT_MUTED};
    border-color: {c.BORDER_SOFT};
}}
QLineEdit[readOnly="true"] {{
    background: {c.CODE_BG};
    color: {c.TEXT_DIM};
    font-family: {MONO};
    font-size: 12px;
}}
QLineEdit#remoteUrl {{
    background: {c.CODE_BG};
    border: {c.BW} solid {c.BORDER};
    color: {c.TEXT};
    font-family: {MONO};
    font-size: 12px;
    padding: 8px 10px;
}}
QLineEdit#remoteUrl:focus {{ border-color: {c.ACCENT}; }}

QDialog#textFileDialog {{
    background: {c.BG};
}}
QLabel#fileDialogTitle {{
    font-size: 14px;
    font-weight: 700;
    color: {c.TEXT};
}}
QLabel#fileDialogPath {{
    font-family: {MONO};
    font-size: 10px;
    color: {c.TEXT_DIM};
}}
QLabel#fileDialogFormat {{
    font-size: 10px;
    color: {c.TEXT_MUTED};
}}
QPlainTextEdit#workspaceEditor {{
    background: {c.CODE_BG};
    border: {c.BW} solid {c.BORDER};
    border-radius: 8px;
    selection-background-color: {c.SELECTION};
    font-family: {MONO};
    font-size: 12px;
    color: {c.CODE_TEXT};
    padding: 8px;
}}
QPlainTextEdit#workspaceEditor:focus {{
    border-color: {c.ACCENT};
}}

/* ---------- Card de alterações propostas ---------- */
QFrame#actionCard {{
    background: {c.SURFACE_ALT};
    border: {c.BW} solid {c.BORDER};
    border-left: 3px solid {c.ACCENT};
    border-radius: 10px;
}}
QLabel#actionTitle {{ font-size: 12px; font-weight: 700; color: {c.ACCENT}; }}
QLabel#actionLine {{ font-family: {MONO}; font-size: 11px; color: {c.TEXT_DIM};
                     padding-left: 4px; }}
QLabel#actionWarn {{ font-size: 11px; color: {c.WARNING}; }}
QLabel#systemNote {{
    font-family: {MONO};
    font-size: 11px;
    color: {c.TEXT_DIM};
    background: {c.SURFACE};
    border: {c.BW} solid {c.BORDER_SOFT};
    border-radius: 8px;
    padding: 7px 12px;
    margin: 3px 0;
}}
QLabel#systemOk {{
    font-family: {MONO};
    font-size: 11px;
    color: {c.SUCCESS};
    background: {c.SUCCESS_SOFT};
    border: {c.BW} solid {c.SUCCESS_LINE};
    border-radius: 8px;
    padding: 7px 12px;
    margin: 3px 0;
}}
QLabel#dangerHint {{ font-size: 12px; color: {c.DANGER}; }}
QToolButton#actionApply {{
    background: {c.ACCENT};
    border: none;
    border-radius: 7px;
    color: {c.ON_ACCENT};
    padding: 6px 14px;
    font-size: 12px;
    font-weight: 700;
}}
QToolButton#actionApply:hover {{ background: {c.ACCENT_HOVER}; }}
QToolButton#actionApply:pressed {{ background: {c.ACCENT_PRESSED}; }}
QToolButton#actionApply:disabled {{ background: {c.SURFACE_HIGH}; color: {c.TEXT_MUTED}; }}

/* ---------- Decisões ----------
 * Âmbar = recomendação do DeepSeek. Verde = sua escolha. */
QFrame#decisionCard {{
    background: {c.SURFACE_ALT};
    border: {c.BW} solid {c.BORDER_STRONG};
    border-left: 3px solid {c.ACCENT};
    border-radius: 12px;
}}
QFrame#decisionCard[estado="resolvida"] {{
    border-color: {c.SUCCESS_LINE};
    border-left: 3px solid {c.SUCCESS};
}}
QFrame#decisionCard[estado="cancelada"] {{
    border-color: {c.BORDER};
    border-left: 3px solid {c.TEXT_MUTED};
}}
QLabel#decisionTitle {{
    color: {c.ACCENT};
    font-size: 10px;
    font-weight: 800;
    letter-spacing: 1.2px;
}}
QFrame#decisionCard[estado="resolvida"] QLabel#decisionTitle {{ color: {c.SUCCESS}; }}
QFrame#decisionCard[estado="cancelada"] QLabel#decisionTitle {{ color: {c.TEXT_MUTED}; }}
QLabel#decisionQuestion {{
    color: {c.TEXT};
    font-size: 14px;
    font-weight: 600;
}}
QToolButton#decisionOption {{
    background: {c.SURFACE};
    border: {c.BW} solid {c.BORDER};
    border-radius: 9px;
    padding: 10px 12px;
    text-align: left;
    font-size: 13px;
    color: {c.TEXT};
}}
QToolButton#decisionOption:hover {{
    background: {c.SURFACE_HIGH};
    border-color: {c.ACCENT};
}}
QToolButton#decisionOption:pressed {{
    background: {c.SURFACE_PRESSED};
    border-color: {c.ACCENT};
}}
QToolButton#decisionOption[recomendada="true"] {{
    background: {c.RECOMMEND_SOFT};
    border: {c.BW} solid {c.RECOMMEND};
    color: {c.TEXT};
    font-weight: 600;
}}
QToolButton#decisionOption[recomendada="true"]:hover {{
    background: {c.RECOMMEND_HOVER};
}}
QToolButton#decisionOption:disabled {{
    color: {c.TEXT_MUTED};
    background: {c.SURFACE};
    border-color: {c.BORDER_SOFT};
}}
QToolButton#decisionOption[recomendada="true"]:disabled {{
    color: {c.RECOMMEND_FADED};
    background: {c.SURFACE};
    border: {c.BW} dashed {c.RECOMMEND_FADED_LINE};
}}
QToolButton#decisionOption[escolhida="true"]:disabled {{
    background: {c.SUCCESS_SOFT};
    border: 2px solid {c.SUCCESS};
    color: {c.TEXT};
    font-weight: 700;
}}
QLabel#decisionRecommendation {{
    background: {c.RECOMMEND_SOFT};
    border: {c.BW} solid {c.RECOMMEND_LINE};
    border-radius: 8px;
    color: {c.RECOMMEND_TEXT};
    font-size: 12px;
    padding: 7px 10px;
}}
QLabel#decisionChosen {{
    background: {c.SUCCESS_SOFT};
    border: {c.BW} solid {c.SUCCESS_LINE};
    border-radius: 8px;
    color: {c.TEXT};
    font-size: 12px;
    padding: 7px 10px;
}}
QLabel#decisionVerdict {{
    font-size: 11px;
    font-weight: 700;
    color: {c.TEXT_DIM};
}}
QLabel#decisionVerdict[tom="segue"] {{ color: {c.SUCCESS}; }}
QLabel#decisionVerdict[tom="diverge"] {{ color: {c.RECOMMEND}; }}
QToolButton#decisionOther {{
    background: transparent;
    border: {c.BW} dashed {c.BORDER_STRONG};
    border-radius: 8px;
    color: {c.TEXT_DIM};
    padding: 6px 10px;
    font-size: 12px;
}}
QToolButton#decisionOther:hover {{ color: {c.TEXT}; border-color: {c.ACCENT}; }}
QToolButton#decisionOther:pressed {{ color: {c.ACCENT}; }}
QToolButton#decisionOther:disabled {{ color: {c.TEXT_MUTED}; border-color: {c.BORDER_SOFT}; }}
QToolButton#decisionAttach {{
    background: {c.SURFACE};
    border: {c.BW} solid {c.BORDER};
    border-radius: 8px;
    color: {c.TEXT_DIM};
    padding: 6px 10px;
    font-size: 12px;
}}
QToolButton#decisionAttach:hover {{ color: {c.TEXT}; border-color: {c.ACCENT}; }}
QToolButton#decisionAttach:disabled {{ color: {c.TEXT_MUTED}; border-color: {c.BORDER_SOFT}; }}

QDialog#decisionDialog {{
    background: {c.SURFACE};
    border: {c.BW} solid {c.ACCENT};
}}
QLabel#decisionDialogTitle {{
    color: {c.ACCENT};
    font-size: 11px;
    font-weight: 800;
    letter-spacing: 1px;
}}
QLabel#decisionDialogQuestion {{
    background: {c.SURFACE_ALT};
    border: {c.BW} solid {c.BORDER};
    border-left: 3px solid {c.ACCENT};
    border-radius: 7px;
    color: {c.TEXT};
    padding: 9px 11px;
}}
QPlainTextEdit#decisionInput, QLineEdit#decisionInput {{
    background: {c.BG};
    border: {c.BW} solid {c.BORDER};
    border-radius: 9px;
    color: {c.TEXT};
    padding: 9px 10px;
    selection-background-color: {c.SELECTION};
    font-size: 13px;
}}
QPlainTextEdit#decisionInput {{ min-height: 82px; }}
QPlainTextEdit#decisionInput:focus, QLineEdit#decisionInput:focus {{ border-color: {c.ACCENT}; }}
QPushButton#decisionConfirm {{
    background: {c.ACCENT};
    border: none;
    color: {c.ON_ACCENT};
    font-weight: 700;
    padding: 7px 16px;
}}
QPushButton#decisionConfirm:hover {{ background: {c.ACCENT_HOVER}; }}
QPushButton#decisionConfirm:pressed {{ background: {c.ACCENT_PRESSED}; }}
QPushButton#decisionConfirm:disabled {{ background: {c.SURFACE_HIGH}; color: {c.TEXT_MUTED}; }}
QPushButton#decisionCancel {{
    background: transparent;
    color: {c.TEXT_DIM};
}}
QPushButton#decisionCancel:hover {{ background: {c.SURFACE_HIGH}; color: {c.TEXT}; }}
QPushButton#decisionCancel:pressed {{ background: {c.SURFACE_PRESSED}; }}

QTextBrowser {{
    background: {c.CODE_BG};
    border: {c.BW} solid {c.BORDER};
    border-radius: 8px;
}}

/* ---------- Terminal ---------- */
QFrame#terminal {{ background: {c.CODE_BG}; border-top: {c.BW} solid {c.BORDER}; }}
QFrame#terminalHeader {{
    background: {c.SURFACE};
    border-bottom: {c.BW} solid {c.BORDER};
}}
QLabel#terminalCwd {{
    font-family: {MONO};
    font-size: 11px;
    color: {c.TEXT_DIM};
}}
QPlainTextEdit#terminalSaida {{
    background: {c.CODE_BG};
    border: none;
    font-family: {MONO};
    font-size: 12px;
    color: {c.CODE_TEXT};
    padding: 6px 10px;
}}
QLineEdit#terminalEntrada {{
    background: {c.SURFACE};
    border: none;
    border-top: {c.BW} solid {c.BORDER_SOFT};
    font-family: {MONO};
    font-size: 12px;
    color: {c.TEXT};
    padding: 7px 10px;
    border-radius: 0;
}}
QLineEdit#terminalEntrada:focus {{ border-top-color: {c.ACCENT}; }}

QSplitter::handle:vertical {{ background: {c.BORDER_SOFT}; height: 1px; }}
QSplitter::handle:horizontal {{ background: {c.BORDER_SOFT}; width: 1px; }}
QSplitter::handle:hover {{ background: {c.ACCENT}; }}

/* ---------- Painel lateral (Projeto / Vault / Habilidades) ---------- */
QWidget#workspacePage {{ background: {c.SURFACE}; }}
QTabWidget#workspaceTabs::pane {{
    background: {c.SURFACE};
    border: none;
    border-top: {c.BW} solid {c.BORDER};
}}
QTabWidget#workspaceTabs QTabBar {{ background: {c.SURFACE}; }}
QTabWidget#workspaceTabs QTabBar::tab {{
    background: transparent;
    color: {c.TEXT_DIM};
    border: none;
    border-bottom: 2px solid transparent;
    padding: 8px 12px;
    min-width: 42px;
    font-weight: 600;
}}
QTabWidget#workspaceTabs QTabBar::tab:selected {{
    color: {c.TEXT};
    border-bottom-color: {c.ACCENT};
}}
QTabWidget#workspaceTabs QTabBar::tab:hover:!selected {{
    color: {c.TEXT};
    background: {c.SURFACE_ALT};
}}
QTabWidget#workspaceTabs QTabBar::tab:pressed {{
    background: {c.SURFACE_PRESSED};
}}
QTreeWidget#projectTree, QTreeWidget#vaultTree {{
    background: {c.SURFACE};
    alternate-background-color: {c.SURFACE};
    color: {c.TEXT};
    border: {c.BW} solid {c.BORDER_SOFT};
    border-radius: 8px;
    outline: none;
}}
QTreeWidget#projectTree::item, QTreeWidget#vaultTree::item {{ padding: 4px 2px; border-radius: 4px; }}
QTreeWidget#projectTree::item:hover, QTreeWidget#vaultTree::item:hover {{
    background: {c.SURFACE_HIGH};
}}
QTreeWidget#projectTree::item:selected, QTreeWidget#vaultTree::item:selected {{
    background: {c.ACCENT_SOFT};
    color: {c.TEXT};
}}
QTreeWidget#projectTree QHeaderView::section,
QTreeWidget#vaultTree QHeaderView::section {{
    background: {c.SURFACE};
    color: {c.TEXT_MUTED};
    border: none;
    border-bottom: {c.BW} solid {c.BORDER_SOFT};
    padding: 6px 6px;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.6px;
}}

/* ---------- Composer ---------- */
QComboBox#responseFormat {{
    background: {c.SURFACE_ALT};
    color: {c.TEXT};
    border: {c.BW} solid {c.BORDER};
    border-radius: 6px;
    padding: 3px 8px;
    min-width: 112px;
    font-size: 11px;
}}
QComboBox#responseFormat:hover:!disabled {{ border-color: {c.ACCENT}; }}
QComboBox#responseFormat:disabled {{
    background: {c.SURFACE};
    color: {c.TEXT_DIM};
}}
QAbstractItemView#responseFormatOptions {{
    background: {c.SURFACE_ALT};
    color: {c.TEXT};
    border: {c.BW} solid {c.BORDER};
    outline: none;
    selection-background-color: {c.ACCENT_SOFT};
    selection-color: {c.TEXT};
}}
QAbstractItemView#responseFormatOptions::item {{
    min-height: 22px;
    padding: 3px 8px;
}}
QAbstractItemView#responseFormatOptions::item:hover {{
    background: {c.SURFACE_HIGH};
    color: {c.TEXT};
}}

QFrame#composer {{ background: {c.SURFACE}; border-top: {c.BW} solid {c.BORDER}; }}
QLabel#composerMeta {{ color: {c.TEXT_MUTED}; font-size: 11px; }}
QPushButton#composerMini {{
    background: transparent;
    border: {c.BW} solid {c.BORDER};
    border-radius: 6px;
    color: {c.TEXT_DIM};
    padding: 3px 9px;
    font-size: 11px;
}}
QPushButton#composerMini:hover {{ color: {c.TEXT}; border-color: {c.ACCENT}; }}
QPushButton#composerMini:disabled {{ color: {c.TEXT_MUTED}; border-color: {c.BORDER_SOFT}; }}
QLabel#accessSummary, QLabel#queueStatus {{
    color: {c.TEXT_DIM};
    font-size: 11px;
    padding: 0 6px;
}}
QLabel#queueStatus {{
    color: {c.ACCENT};
    font-weight: 700;
    background: {c.ACCENT_SOFT};
    border: {c.BW} solid {c.USER_BORDER};
    border-radius: 9px;
    padding: 1px 8px;
}}

/* ---------- Fila de envio (acima do composer) ---------- */
QFrame#queuePanel {{
    background: {c.SURFACE_ALT};
    border: {c.BW} solid {c.BORDER};
    border-radius: 10px;
}}
QLabel#queueTitle {{
    color: {c.TEXT_DIM};
    font-size: 10px;
    font-weight: 800;
    letter-spacing: 1.2px;
}}
QFrame#queueItem {{
    background: {c.SURFACE};
    border: {c.BW} solid {c.BORDER_SOFT};
    border-radius: 8px;
}}
QFrame#queueItem:hover {{ border-color: {c.BORDER_STRONG}; }}
QLabel#queueIndex {{
    background: {c.ACCENT_SOFT};
    color: {c.ACCENT};
    border-radius: 9px;
    font-size: 10px;
    font-weight: 800;
}}
QLabel#queueText {{ color: {c.TEXT}; font-size: 12px; }}
QLabel#queueMeta {{ color: {c.TEXT_MUTED}; font-size: 11px; }}
QToolButton#queueCancel {{
    background: transparent;
    border: {c.BW} solid transparent;
    border-radius: 6px;
    color: {c.TEXT_MUTED};
    padding: 2px 7px;
    font-size: 12px;
}}
QToolButton#queueEdit {{
    background: transparent;
    border: {c.BW} solid transparent;
    border-radius: 6px;
    color: {c.TEXT_MUTED};
    padding: 2px 7px;
    font-size: 12px;
}}
QToolButton#queueEdit:hover {{ color: {c.ACCENT}; border-color: {c.ACCENT}; background: {c.ACCENT_SOFT}; }}
QToolButton#queueCancel:hover {{ color: {c.DANGER}; border-color: {c.DANGER}; background: {c.DANGER_SOFT}; }}
QToolButton#queueClear {{
    background: transparent;
    border: none;
    color: {c.TEXT_MUTED};
    font-size: 11px;
    padding: 2px 4px;
}}
QToolButton#queueClear:hover {{ color: {c.DANGER}; }}

/* ---------- Chips de anexo (acima do campo de texto) ---------- */
QFrame#barraAnexos {{ background: transparent; }}
QFrame#chipAnexo {{
    background: {c.SURFACE_HIGH};
    border: {c.BW} solid {c.BORDER};
    border-radius: 999px;
}}
QLabel#chipTexto, QToolButton#chipTexto {{ font-size: 11px; color: {c.TEXT_DIM}; }}
QToolButton#chipTexto:hover {{ color: {c.TEXT}; }}
QToolButton#chipTexto:pressed {{ color: {c.ACCENT}; }}
QToolButton#chipFechar {{
    background: transparent;
    border: none;
    color: {c.TEXT_MUTED};
    font-size: 11px;
    padding: 0 4px;
}}
QToolButton#chipFechar:hover {{ color: {c.DANGER}; }}
QToolButton#chipFechar:pressed {{ color: {c.DANGER_PRESSED}; }}
QPlainTextEdit#input {{
    background: {c.SURFACE_ALT};
    border: {c.BW} solid {c.BORDER};
    border-radius: 12px;
    padding: 10px 12px;
    font-size: 13px;
    selection-background-color: {c.SELECTION};
}}
QPlainTextEdit#input:focus {{ border-color: {c.ACCENT}; background: {c.BG}; }}
QPlainTextEdit#input:disabled {{ color: {c.TEXT_MUTED}; background: {c.SURFACE}; }}
QPushButton#send {{
    background: {c.ACCENT};
    border: none;
    border-radius: 10px;
    color: {c.ON_ACCENT};
    padding: 9px 20px;
    font-size: 13px;
    font-weight: 700;
}}
QPushButton#send:hover {{ background: {c.ACCENT_HOVER}; }}
QPushButton#send:pressed {{ background: {c.ACCENT_PRESSED}; }}
QPushButton#send:disabled {{ background: {c.SURFACE_HIGH}; color: {c.TEXT_MUTED}; }}

/* ---------- Diálogos e permissões ---------- */
QDialog {{ background: {c.SURFACE}; }}
QLabel#permissionSection {{
    color: {c.TEXT};
    font-size: 13px;
    font-weight: 700;
}}
QLabel#permissionNotice {{
    background: {c.SURFACE_HIGH};
    border: {c.BW} solid {c.BORDER};
    border-left: 3px solid {c.ACCENT};
    border-radius: 6px;
    color: {c.TEXT};
    padding: 8px 10px;
}}
QLabel#permissionHint {{
    color: {c.ACCENT};
    font-size: 12px;
    font-weight: 600;
}}
QComboBox#permissionMode {{
    background: {c.SURFACE_ALT};
    color: {c.TEXT};
    border: {c.BW} solid {c.BORDER};
    border-radius: 7px;
    padding: 7px 10px;
    min-height: 24px;
}}
QComboBox#permissionMode:hover, QComboBox#permissionMode:focus {{
    border-color: {c.ACCENT};
}}
QComboBox#permissionMode::drop-down {{
    border: none;
    width: 28px;
}}
QComboBox#permissionMode QAbstractItemView {{
    background: {c.SURFACE_ALT};
    color: {c.TEXT};
    border: {c.BW} solid {c.BORDER};
    selection-background-color: {c.ACCENT_SOFT};
    selection-color: {c.TEXT};
}}
QTableWidget#permissionGrants {{
    background: {c.SURFACE_ALT};
    alternate-background-color: {c.SURFACE};
    color: {c.TEXT};
    gridline-color: {c.BORDER};
    border: {c.BW} solid {c.BORDER};
    border-radius: 6px;
    selection-background-color: {c.ACCENT_SOFT};
    selection-color: {c.TEXT};
    outline: none;
}}
QTableWidget#permissionGrants::item {{
    padding: 6px 8px;
    border-bottom: {c.BW} solid {c.BORDER_SOFT};
}}
QTableWidget#permissionGrants::item:hover {{
    background: {c.SURFACE_HIGH};
}}
QTableWidget#permissionGrants QHeaderView::section {{
    background: {c.SURFACE_HIGH};
    color: {c.TEXT};
    border: none;
    border-bottom: {c.BW} solid {c.BORDER};
    padding: 7px 8px;
    font-weight: 700;
}}
QCheckBox#folderPermission {{
    spacing: 0;
    padding: 3px;
}}
QCheckBox#folderPermission::indicator {{
    width: 20px;
    height: 20px;
}}
QCheckBox#folderPermission::indicator:unchecked {{
    background: {c.SURFACE};
    border: {c.BW} solid {c.TEXT_MUTED};
    border-radius: 5px;
}}
QCheckBox#folderPermission::indicator:checked {{
    background: {c.ACCENT};
    border: {c.BW} solid {c.ACCENT};
    border-radius: 5px;
}}
QCheckBox {{
    spacing: 8px;
}}
QCheckBox::indicator {{
    width: 18px;
    height: 18px;
}}
QCheckBox::indicator:unchecked {{
    background: {c.SURFACE_ALT};
    border: {c.BW} solid {c.TEXT_MUTED};
    border-radius: 5px;
}}
QCheckBox::indicator:checked {{
    background: {c.ACCENT};
    border: {c.BW} solid {c.ACCENT};
    border-radius: 5px;
}}
QCheckBox:disabled {{
    color: {c.TEXT_DIM};
}}
QListWidget {{
    background: {c.SURFACE_ALT};
    border: {c.BW} solid {c.BORDER};
    border-radius: 8px;
    font-size: 12px;
}}
QListWidget::item {{ padding: 6px 8px; border-radius: 6px; }}
QListWidget::item:hover {{ background: {c.SURFACE_HIGH}; }}
QListWidget::item:selected {{ background: {c.ACCENT_SOFT}; color: {c.TEXT}; }}

QMenu {{
    background: {c.SURFACE_ALT};
    border: {c.BW} solid {c.BORDER_STRONG};
    border-radius: 8px;
    padding: 4px;
}}
QMenu::item {{ padding: 6px 18px 6px 12px; border-radius: 5px; }}
QMenu::item:selected {{ background: {c.ACCENT_SOFT}; color: {c.TEXT}; }}
QMenu::separator {{ height: 1px; background: {c.BORDER}; margin: 4px 6px; }}

/* ---------- Habilidades (terceira aba do workspace) ---------- */
QWidget#skillsPage {{ background: {c.SURFACE}; }}
QWidget#skillsPage[arrastando="true"] {{ background: {c.ACCENT_SOFT}; }}
QLabel#skillsHint {{
    font-size: 11px;
    color: {c.TEXT_DIM};
}}
QLabel#skillsHintOn {{
    font-size: 11px;
    color: {c.ACCENT};
}}
QLabel#skillsHintOff {{
    font-size: 11px;
    color: {c.TEXT_MUTED};
}}
QLabel#skillsStatus {{
    font-size: 11px;
    color: {c.TEXT_DIM};
}}
QLabel#skillsSaved {{
    font-size: 11px;
    color: {c.TEXT_MUTED};
}}
QLabel#skillsSavedError {{
    font-size: 11px;
    color: {c.DANGER};
}}
QLabel#skillsTitle {{
    font-size: 15px;
    font-weight: 700;
    color: {c.TEXT};
}}
QLabel#skillsSlug {{
    font-family: {MONO};
    font-size: 10px;
    color: {c.TEXT_MUTED};
}}
QPushButton#skillsImport {{
    background: {c.ACCENT_SOFT};
    border: {c.BW} solid {c.USER_BORDER};
    color: {c.TEXT};
}}
QPushButton#skillsImport:hover {{ border-color: {c.ACCENT}; background: {c.ACCENT_SOFT_HOVER}; }}
QPushButton#skillsImport::menu-indicator {{ subcontrol-position: right center; right: 8px; }}
QFrame#skillsItem {{
    background: transparent;
    border: {c.BW} solid transparent;
    border-radius: 8px;
}}
QFrame#skillsItem:hover {{
    background: {c.SURFACE_HIGH};
}}
QFrame#skillsItem[selecionado="true"] {{
    background: {c.ACCENT_SOFT};
    border-color: {c.USER_BORDER};
}}
QLabel#skillsIcon {{
    background: {c.SURFACE_HIGH};
    color: {c.TEXT_DIM};
    border: {c.BW} solid {c.BORDER};
    border-radius: 8px;
    font-family: {MONO};
    font-size: 11px;
    font-weight: 700;
}}
QFrame#skillsItem[habilitada="true"] QLabel#skillsIcon {{
    color: {c.ACCENT};
    border-color: {c.ACCENT};
    background: {c.ACCENT_SOFT};
}}
QLabel#skillsItemName {{
    color: {c.TEXT};
    font-size: 12px;
    font-weight: 600;
}}
QLabel#skillsItemDesc {{
    color: {c.TEXT_DIM};
    font-size: 11px;
}}
QListWidget#skillsList {{
    background: {c.SURFACE};
    border: none;
    border-radius: 0;
    padding: 4px;
    font-size: 12px;
}}
QListWidget#skillsList::item {{
    padding: 0;
    border: none;
}}
QListWidget#skillsList::item:selected {{
    background: transparent;
}}
"""
