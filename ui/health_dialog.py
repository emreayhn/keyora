"""Şifre sağlığı raporu — zayıf, tekrar kullanılan ve eskimiş şifreler."""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QMessageBox,
    QPushButton, QTabWidget, QVBoxLayout, QWidget,
)

from core import health
from core.vault import EntrySummary, Vault
from ui import theme


class HealthDialog(QDialog):
    """Rapor ekranı. Bir kayıt düzenlenmek istenince `edit_requested` yayar;
    çağıran düzenlemeyi yaptıktan sonra `refresh()` çağırır."""

    edit_requested = Signal(int)

    def __init__(self, vault: Vault, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.vault = vault
        self.setWindowTitle("Şifre Sağlığı")
        self.setMinimumSize(620, 520)
        self._build_ui()
        self.loaded = self.refresh()

    # ---------- UI ----------

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 16)
        layout.setSpacing(12)

        title = QLabel("Şifre Sağlığı")
        title.setProperty("role", "title")

        self.score_label = QLabel()
        self.score_label.setStyleSheet("font-size: 28px; font-weight: 600;")
        self.summary_label = QLabel()
        self.summary_label.setProperty("role", "muted")
        self.summary_label.setWordWrap(True)

        score_row = QHBoxLayout()
        score_row.addWidget(self.score_label)
        score_row.addSpacing(12)
        score_row.addWidget(self.summary_label, 1)

        self.tabs = QTabWidget()
        self.weak_list = self._make_list()
        self.reused_list = self._make_list()
        self.old_list = self._make_list()
        self.tabs.addTab(self.weak_list, "")
        self.tabs.addTab(self.reused_list, "")
        self.tabs.addTab(self.old_list, "")

        note = QLabel(
            "Rapor tamamen bu bilgisayarda hesaplanır; hiçbir veri dışarı gönderilmez. "
            "Bir kayda çift tıklayarak şifresini değiştirebilirsiniz. İçe aktarılan "
            "kayıtların yaşı içe aktarma tarihinden itibaren sayılır."
        )
        note.setProperty("role", "muted")
        note.setWordWrap(True)

        self.edit_btn = QPushButton("Seçili Kaydı Düzenle")
        self.edit_btn.setProperty("role", "primary")
        self.edit_btn.clicked.connect(self._on_edit_selected)
        close_btn = QPushButton("Kapat")
        close_btn.clicked.connect(self.accept)
        btns = QHBoxLayout()
        btns.addStretch()
        btns.addWidget(close_btn)
        btns.addWidget(self.edit_btn)

        layout.addWidget(title)
        layout.addLayout(score_row)
        layout.addWidget(self.tabs, 1)
        layout.addWidget(note)
        layout.addLayout(btns)

    def _make_list(self) -> QListWidget:
        lst = QListWidget()
        lst.setWordWrap(True)
        lst.setAlternatingRowColors(False)
        lst.itemDoubleClicked.connect(self._on_item_activated)
        return lst

    # ---------- data ----------

    def refresh(self) -> bool:
        """Raporu yeniden hesaplar ve listeleri doldurur. Başarısızsa uyarır, False döner."""
        try:
            report = health.analyze(self.vault)
        except Exception as exc:
            QMessageBox.critical(self, "Hata", f"Şifre sağlığı hesaplanamadı: {exc}")
            return False

        c = theme.palette()
        color = (c["accent"] if report.score >= 80
                 else c["warning"] if report.score >= 50 else c["danger"])
        self.score_label.setText(f"%{report.score}")
        self.score_label.setStyleSheet(f"font-size: 28px; font-weight: 600; color: {color};")
        if report.total == 0:
            self.summary_label.setText("Kasada henüz kayıt yok.")
        else:
            self.summary_label.setText(
                f"{report.total} kaydın {report.healthy} tanesi sorunsuz."
            )

        weak_rows = [(i.entry, f"⚠ {i.detail}") for i in report.unreadable]
        weak_rows += [(i.entry, i.detail) for i in report.weak]
        self._fill(self.weak_list, weak_rows, "Zayıf şifre yok.")

        reused_rows = []
        for group in report.reused:
            for entry in group:
                others = ", ".join(e.app_name for e in group if e.id != entry.id)
                reused_rows.append((entry, f"Aynı şifre şunlarda da kullanılıyor: {others}"))
        self._fill(self.reused_list, reused_rows, "Tekrar kullanılan şifre yok.")

        self._fill(self.old_list, [
            (i.entry, i.detail) for i in report.old
        ], f"{health.OLD_AFTER_DAYS} günden eski şifre yok.")

        self.tabs.setTabText(0, f"Zayıf ({len(weak_rows)})")
        self.tabs.setTabText(1, f"Tekrar kullanılan ({len(reused_rows)})")
        self.tabs.setTabText(2, f"Eski ({len(report.old)})")

        # İlk sorunlu sekmeyi öne getir
        for index, count in enumerate((len(weak_rows), len(reused_rows), len(report.old))):
            if count:
                self.tabs.setCurrentIndex(index)
                break
        return True

    def _fill(
        self,
        lst: QListWidget,
        rows: list[tuple[EntrySummary, str]],
        empty_text: str,
    ) -> None:
        lst.clear()
        if not rows:
            item = QListWidgetItem(f"✓ {empty_text}")
            item.setFlags(Qt.NoItemFlags)
            lst.addItem(item)
            return
        for entry, detail in rows:
            item = QListWidgetItem(f"{entry.app_name} — {entry.username}\n    {detail}")
            item.setData(Qt.UserRole, entry.id)
            lst.addItem(item)

    # ---------- actions ----------

    def _on_item_activated(self, item: QListWidgetItem) -> None:
        entry_id = item.data(Qt.UserRole)
        if entry_id is not None:
            self.edit_requested.emit(entry_id)

    def _on_edit_selected(self) -> None:
        lst = self.tabs.currentWidget()
        if isinstance(lst, QListWidget) and lst.currentItem() is not None:
            self._on_item_activated(lst.currentItem())
