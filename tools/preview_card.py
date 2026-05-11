"""Tek seferlik görsel doğrulama: her tema için bir EntryCard görüntüsü kaydeder."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication, QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget,
)

from ui import icons, theme
from ui.components.entry_card import (
    EntryCard, COL_ACTION_W, COL_APP_STR, COL_FAV_W, COL_PW_STR, COL_USER_STR,
)


def _make_header() -> QWidget:
    header = QFrame()
    header.setObjectName("ColumnHeader")
    c = theme.palette()
    header.setStyleSheet(f"""
        QFrame#ColumnHeader QLabel {{
            color: {c['text_muted']}; font-size: 11px; font-weight: 600;
            letter-spacing: 0.5px;
        }}
    """)
    row = QHBoxLayout(header)
    row.setContentsMargins(12, 6, 12, 6)
    row.setSpacing(10)
    spacer = QLabel(" "); spacer.setFixedWidth(COL_FAV_W); row.addWidget(spacer)
    row.addWidget(QLabel("UYGULAMA"), COL_APP_STR)
    row.addWidget(QLabel("KULLANICI ADI"), COL_USER_STR)
    row.addWidget(QLabel("ŞİFRE"), COL_PW_STR)
    acts = QLabel("EYLEMLER"); acts.setAlignment(Qt.AlignCenter)
    acts.setFixedWidth(COL_ACTION_W * 3 + 20)
    row.addWidget(acts)
    return header


def _render_theme(app: QApplication, theme_name: str, out_path: Path) -> None:
    theme.set_active(theme_name)
    icons.clear_cache()
    app.setStyleSheet(theme.stylesheet())

    container = QWidget()
    container.setStyleSheet(f"background-color: {theme.palette()['bg_primary']};")
    container.resize(900, 230)
    v = QVBoxLayout(container)
    v.setContentsMargins(16, 16, 16, 16)
    v.setSpacing(6)
    v.addWidget(_make_header())
    v.addWidget(EntryCard(1, "GitHub", "emre@example.com", True))
    v.addWidget(EntryCard(2, "Alfa3",  "admin",            False))
    v.addStretch(1)

    container.show()
    app.processEvents()
    container.grab().save(str(out_path), "PNG")
    container.close()
    print(f"OK: {out_path}")


def main() -> int:
    app = QApplication(sys.argv)
    out_dir = ROOT / "resources"
    out_dir.mkdir(parents=True, exist_ok=True)
    _render_theme(app, theme.DARK_NAME,  out_dir / "preview-dark.png")
    _render_theme(app, theme.LIGHT_NAME, out_dir / "preview-light.png")
    return 0


if __name__ == "__main__":
    sys.exit(main())
