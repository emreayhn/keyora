"""Keyora tema sistemi — pastel Dark + pastel Light, anında geçiş."""
from __future__ import annotations

DARK_NAME = "dark"
LIGHT_NAME = "light"
DEFAULT = DARK_NAME

# ---------- pastel paletler ----------

DARK_PALETTE: dict[str, str] = {
    "bg_primary":     "#1F1D2E",   # plum-tinted dark
    "bg_secondary":   "#2B2842",   # panel
    "bg_card":        "#3A3756",   # card surface / button base
    "field_bg":       "#171529",   # input alanı (kart içi)
    "accent":         "#E8A0B5",   # dusty rose (pastel)
    "accent_hover":   "#F2BAC8",
    "accent_strong":  "#D98298",   # dolu primary buton metniyle kontrast
    "text_primary":   "#ECE8F0",
    "text_on_accent": "#1F1D2E",   # accent üstüne yazılan metin
    "text_muted":     "#9A93A8",
    "success":        "#A8D8B9",
    "warning":        "#F5C99B",
    "danger":         "#F4A3A3",
    "border":         "#3E3B58",
    "border_hover":   "#5A5478",
}

LIGHT_PALETTE: dict[str, str] = {
    "bg_primary":     "#FAF6F2",   # warm cream
    "bg_secondary":   "#F2EAEC",   # blush panel
    "bg_card":        "#FFFFFF",
    "field_bg":       "#FFFFFF",
    "accent":         "#D98494",   # dusty rose
    "accent_hover":   "#C9707F",
    "accent_strong":  "#C9707F",
    "text_primary":   "#2F2A3A",
    "text_on_accent": "#FFFFFF",
    "text_muted":     "#7B7488",
    "success":        "#6FB37D",
    "warning":        "#D9A671",
    "danger":         "#D87A7A",
    "border":         "#E3D8DA",
    "border_hover":   "#CFC0C4",
}

_PALETTES = {DARK_NAME: DARK_PALETTE, LIGHT_NAME: LIGHT_PALETTE}

_active_name: str = DEFAULT


# ---------- API ----------

def available_themes() -> list[tuple[str, str]]:
    """[(internal_name, display_label), ...]."""
    return [(DARK_NAME, "Koyu"), (LIGHT_NAME, "Açık")]


def active_name() -> str:
    return _active_name


def set_active(name: str) -> None:
    """Geçerli temayı değiştirir. Geçersiz isim DEFAULT'a düşer."""
    global _active_name
    _active_name = name if name in _PALETTES else DEFAULT


def palette() -> dict[str, str]:
    return _PALETTES[_active_name]


# ---------- uygulama geneli stylesheet ----------

def stylesheet() -> str:
    c = palette()
    return f"""
    QWidget {{
        background-color: {c['bg_primary']};
        color: {c['text_primary']};
        font-family: 'Segoe UI', sans-serif;
        font-size: 13px;
    }}
    QFrame#Card, QFrame#Panel {{
        background-color: {c['bg_secondary']};
        border-radius: 8px;
    }}
    QLineEdit, QTextEdit, QComboBox, QSpinBox {{
        background-color: {c['bg_secondary']};
        color: {c['text_primary']};
        border: 1px solid {c['border']};
        border-radius: 6px;
        padding: 8px 10px;
        selection-background-color: {c['accent']};
        selection-color: {c['text_on_accent']};
    }}
    QLineEdit:focus, QTextEdit:focus, QComboBox:focus, QSpinBox:focus {{
        border: 1px solid {c['accent']};
    }}
    QPushButton {{
        background-color: {c['bg_card']};
        color: {c['text_primary']};
        border: none;
        border-radius: 6px;
        padding: 8px 16px;
        font-weight: 500;
        min-height: 18px;
    }}
    QPushButton:hover {{
        background-color: {c['border_hover']};
    }}
    QPushButton:pressed {{
        background-color: {c['accent_hover']};
    }}
    QPushButton[role="primary"] {{
        background-color: {c['accent']};
        color: {c['text_on_accent']};
    }}
    QPushButton[role="primary"]:hover {{
        background-color: {c['accent_hover']};
    }}
    QPushButton[role="danger"] {{
        background-color: {c['danger']};
        color: {c['text_on_accent']};
    }}
    QPushButton[role="ghost"] {{
        background-color: transparent;
        color: {c['text_muted']};
    }}
    QPushButton[role="ghost"]:hover {{
        color: {c['text_primary']};
        background-color: {c['bg_secondary']};
    }}
    QListWidget, QTableWidget {{
        background-color: {c['bg_secondary']};
        border: 1px solid {c['border']};
        border-radius: 6px;
        padding: 4px;
    }}
    QListWidget::item {{
        padding: 8px;
        border-radius: 4px;
    }}
    QListWidget::item:selected {{
        background-color: {c['accent']};
        color: {c['text_on_accent']};
    }}
    QListWidget::item:hover {{
        background-color: {c['bg_card']};
    }}
    QLabel[role="muted"] {{
        color: {c['text_muted']};
    }}
    QLabel[role="title"] {{
        font-size: 20px;
        font-weight: 600;
    }}
    QStatusBar {{
        background-color: {c['bg_secondary']};
        color: {c['text_muted']};
    }}
    QMenuBar, QMenu {{
        background-color: {c['bg_secondary']};
        color: {c['text_primary']};
    }}
    QMenuBar::item:selected, QMenu::item:selected {{
        background-color: {c['accent']};
        color: {c['text_on_accent']};
    }}
    QCheckBox::indicator {{
        width: 16px; height: 16px;
    }}
    QScrollBar:vertical {{
        background: {c['bg_primary']};
        width: 10px;
    }}
    QScrollBar::handle:vertical {{
        background: {c['bg_card']};
        border-radius: 4px;
        min-height: 20px;
    }}
    QScrollBar::handle:vertical:hover {{
        background: {c['accent']};
    }}
    """


# Geriye uyumluluk için (eski import'lar görür) — palette() kullanılması tercih edilir.
COLORS = DARK_PALETTE
