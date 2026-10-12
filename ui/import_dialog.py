"""İçe aktarma ekranı — desteklenen biçimler, kolonlar, önizleme ve onay."""
from __future__ import annotations

import csv
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QDialog, QFileDialog, QHBoxLayout, QHeaderView,
    QLabel, QMessageBox, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout,
    QWidget,
)

from core.vault import Vault
from utils import importers


class ImportDialog(QDialog):
    """Dosya seç → önizle → içe aktar. Başarılıysa `accepted` ile kapanır."""

    def __init__(self, vault: Vault, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.vault = vault
        self.imported_count = 0
        self._preview: Optional[importers.ImportPreview] = None
        self.setWindowTitle("İçe Aktar")
        self.setMinimumSize(640, 600)
        self._build_ui()
        self._show_format(0)

    # ---------- UI ----------

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 16)
        layout.setSpacing(10)

        title = QLabel("İçe Aktar")
        title.setProperty("role", "title")
        intro = QLabel(
            "Diğer uygulamanın kendi 'dışa aktar' özelliğiyle aldığınız dosyayı seçin. "
            "Dosya yalnızca bu bilgisayarda okunur; hiçbir yere bağlanılmaz. "
            "Biçim kolon başlıklarından otomatik algılanır."
        )
        intro.setProperty("role", "muted")
        intro.setWordWrap(True)

        self.format_combo = QComboBox()
        for fmt in importers.FORMATS:
            self.format_combo.addItem(fmt.label, fmt.key)
        self.format_combo.currentIndexChanged.connect(self._show_format)
        fmt_row = QHBoxLayout()
        fmt_row.addWidget(QLabel("Biçim rehberi:"))
        fmt_row.addWidget(self.format_combo, 1)

        self.how_to_label = QLabel()
        self.how_to_label.setWordWrap(True)

        self.columns_table = QTableWidget(0, 2)
        self.columns_table.setHorizontalHeaderLabels(["Kolon", "Ne olur"])
        self.columns_table.verticalHeader().setVisible(False)
        self.columns_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.columns_table.setSelectionMode(QAbstractItemView.NoSelection)
        header = self.columns_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.Stretch)

        self.choose_btn = QPushButton("Dosya Seç…")
        self.choose_btn.clicked.connect(self._on_choose)
        self.summary_label = QLabel("Henüz dosya seçilmedi.")
        self.summary_label.setWordWrap(True)
        self.summary_label.setProperty("role", "muted")

        warning = QLabel(
            "⚠ Dışa aktarılan dosya tüm şifreleri DÜZ METİN içerir. İçe aktardıktan "
            "sonra Keyora dosyayı silmeyi önerir. Dosyayı OneDrive gibi eşitlenen bir "
            "klasöre (ör. Masaüstü) kaydettiyseniz buluta da yüklenmiş olabilir."
        )
        warning.setWordWrap(True)

        self.import_btn = QPushButton("İçe Aktar")
        self.import_btn.setProperty("role", "primary")
        self.import_btn.setEnabled(False)
        self.import_btn.clicked.connect(self._on_import)
        cancel_btn = QPushButton("Kapat")
        cancel_btn.clicked.connect(self.reject)
        btns = QHBoxLayout()
        btns.addWidget(self.choose_btn)
        btns.addStretch()
        btns.addWidget(cancel_btn)
        btns.addWidget(self.import_btn)

        layout.addWidget(title)
        layout.addWidget(intro)
        layout.addLayout(fmt_row)
        layout.addWidget(self.how_to_label)
        layout.addWidget(self.columns_table, 1)
        layout.addWidget(warning)
        layout.addWidget(self.summary_label)
        layout.addLayout(btns)

    def _show_format(self, index: int) -> None:
        fmt = importers.FORMATS[index]
        self.how_to_label.setText(f"<b>Nasıl alınır:</b> {fmt.how_to}")
        self.columns_table.setRowCount(len(fmt.columns))
        for row, (col, desc) in enumerate(fmt.columns):
            name_item = QTableWidgetItem(col)
            name_item.setFlags(Qt.ItemIsEnabled)
            desc_item = QTableWidgetItem(desc)
            desc_item.setFlags(Qt.ItemIsEnabled)
            self.columns_table.setItem(row, 0, name_item)
            self.columns_table.setItem(row, 1, desc_item)

    # ---------- actions ----------

    def _on_choose(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "İçe aktarılacak dosyayı seç", "", "CSV (*.csv);;Tüm dosyalar (*)"
        )
        if not path:
            return
        try:
            prepared = importers.preview(self.vault, path)
        except UnicodeDecodeError:
            self._preview = None
            self.import_btn.setEnabled(False)
            self.summary_label.setText(
                "Dosya okunamadı: UTF-8 değil. Uygulamadan yeniden dışa aktarın "
                "ya da dosyayı UTF-8 olarak kaydedin."
            )
            return
        except (ValueError, OSError, RuntimeError, csv.Error) as exc:
            self._preview = None
            self.import_btn.setEnabled(False)
            self.summary_label.setText(f"Dosya okunamadı: {exc}")
            return

        self._preview = prepared
        index = next(i for i, f in enumerate(importers.FORMATS) if f.key == prepared.format.key)
        self.format_combo.setCurrentIndex(index)

        lines = [
            f"<b>{Path(path).name}</b> — algılanan biçim: <b>{prepared.format.label}</b>",
            f"Eklenecek: <b>{len(prepared.rows)}</b> kayıt",
        ]
        if prepared.duplicates:
            lines.append(f"Kasada zaten var, atlanacak: {prepared.duplicates}")
        if prepared.skipped_invalid:
            lines.append(f"Eksik bilgi (şifre/ad), atlanacak: {prepared.skipped_invalid}")
        if prepared.skipped_other_types:
            lines.append(
                f"Giriş olmayan öğe (kart, kimlik, not), atlanacak: {prepared.skipped_other_types}"
            )
        if prepared.malformed:
            lines.append(
                f"Bozuk satır, atlanacak: {prepared.malformed} — kolon sayısı başlıkla "
                "uyuşmuyor (ör. tırnaksız virgül içeren şifre); dosyayı düzeltip yeniden deneyin"
            )
        if prepared.skipped_trash:
            lines.append(f"Çöp kutusundaki kayıt, atlanacak: {prepared.skipped_trash}")
        if prepared.extra_columns:
            cols = ", ".join(sorted(prepared.extra_columns))
            lines.append(f"Tanınmayan kolonlar kaybolmasın diye notlara eklenecek: {cols}")
        if prepared.reprompt:
            lines.append(
                f"{prepared.reprompt} öğede 'parolayı yeniden sor' ayarlıydı; Keyora'da "
                "bu ayar yok (şifreler zaten yalnızca kasa açıkken görünür)"
            )
        if prepared.dropped_totp:
            lines.append(
                f"2FA (TOTP) anahtarı aktarılmayacak: {prepared.dropped_totp} kayıt — "
                "şifreyle aynı kasada tutmak iki adımlı doğrulamayı zayıflatır"
            )
        self.summary_label.setText("<br>".join(lines))
        self.import_btn.setEnabled(bool(prepared.rows))

    def _on_import(self) -> None:
        if self._preview is None:
            return
        prepared = self._preview
        self._preview = None  # düz metin şifreler bellekte gereğinden uzun kalmasın
        source = prepared.path
        lost = prepared.not_carried_over
        try:
            self.imported_count = importers.apply(self.vault, prepared)
        except Exception as exc:
            QMessageBox.critical(
                self, "İçe aktarma başarısız",
                f"Hiçbir kayıt eklenmedi: {exc}",
            )
            self.import_btn.setEnabled(False)
            self.summary_label.setText(
                "İçe aktarma başarısız oldu, hiçbir kayıt eklenmedi. "
                "Tekrar denemek için dosyayı yeniden seçin."
            )
            return
        finally:
            del prepared

        if self.vault.is_locked:
            return  # bu arada kilitlendi: diyalog zaten kapatıldı
        self._offer_delete_source(source, lost)
        if not self.vault.is_locked:
            self.accept()

    def _offer_delete_source(self, source: Path, lost: list[str]) -> None:
        """Kaynak dosyayı silmeyi önerir. Aktarılmayan veri varsa açıkça söyler
        ve varsayılan 'Hayır' olur — o veriler dosyanın tek kopyası olabilir."""
        text = (
            f"{self.imported_count} kayıt içe aktarıldı (öncesinde yedek alındı).\n\n"
            f"'{source.name}' tüm şifreleri düz metin içeriyor."
        )
        if lost:
            text += (
                "\n\nDİKKAT — şunlar Keyora'ya aktarılmadı ve yalnızca bu dosyada "
                "olabilir:\n• " + "\n• ".join(lost) +
                "\n\nBunlara ihtiyacınız yoksa ya da başka bir yerde kopyaları "
                "varsa silebilirsiniz."
            )
        text += "\n\nDosya şimdi silinsin mi? (Geri dönüşüm kutusuna gitmez.)"
        default = QMessageBox.No if lost else QMessageBox.Yes
        answer = QMessageBox.question(
            self, "Kaynak dosya", text, QMessageBox.Yes | QMessageBox.No, default,
        )
        if answer == QMessageBox.Yes and not self.vault.is_locked:
            try:
                importers.delete_source(source)
            except OSError as exc:
                QMessageBox.warning(self, "Silinemedi", f"Dosyayı elle silin: {exc}")

    def done(self, result: int) -> None:
        """Diyalog hangi yolla kapanırsa kapansın önizlemedeki düz metni bırak."""
        self._preview = None
        super().done(result)
