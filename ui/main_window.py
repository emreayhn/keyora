"""Keyora ana pencere — sol panel + arama + entry listesi + auto-lock."""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, QTimer, QEvent
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QLineEdit,
    QPushButton, QListWidget, QListWidgetItem, QLabel, QFrame,
    QMessageBox, QInputDialog, QMenu, QStatusBar, QStackedWidget,
    QScrollArea,
)

from core.vault import Vault, VaultEntry
from ui import icons, theme
from ui.about_dialog import AboutDialog
from ui.components.entry_card import (
    EntryCard,
    COL_FAV_W, COL_APP_STR, COL_USER_STR, COL_PW_STR, COL_ACTION_W,
)
from ui.entry_dialog import EntryDialog
from ui.generator_dialog import GeneratorDialog
from ui.history_dialog import HistoryDialog
from ui.settings_dialog import SettingsDialog
from utils.clipboard import copy_to_clipboard
from utils import csv_io

COUNTDOWN_TICK_MS = 1000


class MainWindow(QMainWindow):
    """Vault açıkken görünen ana ekran."""

    def __init__(self, vault: Vault) -> None:
        super().__init__()
        self.vault = vault
        self.setWindowTitle("Keyora")
        self.resize(1000, 640)

        self._current_category: Optional[int] = None
        self._favorites_only = False
        self._search_text = ""

        self._build_ui()
        self._build_menu()
        self._setup_auto_lock()
        self._reload_categories()
        self._reload_entries()

    # ---------- UI ----------

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(12)

        # Sol panel
        left = QFrame()
        left.setObjectName("Panel")
        left.setFixedWidth(220)
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(12, 12, 12, 12)
        left_layout.setSpacing(8)

        brand = QLabel("Keyora")
        brand.setProperty("role", "title")
        left_layout.addWidget(brand)

        self.all_btn = QPushButton("Tümü")
        self.all_btn.clicked.connect(lambda: self._set_filter(None, False))

        self.fav_btn = QPushButton("⭐ Favoriler")
        self.fav_btn.clicked.connect(lambda: self._set_filter(None, True))

        left_layout.addWidget(self.all_btn)
        left_layout.addWidget(self.fav_btn)
        left_layout.addWidget(QLabel("Kategoriler"))

        self.category_list = QListWidget()
        self.category_list.itemClicked.connect(self._on_category_clicked)
        self.category_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.category_list.customContextMenuRequested.connect(self._on_category_context)
        left_layout.addWidget(self.category_list, 1)

        self.add_cat_btn = QPushButton("+ Kategori")
        self.add_cat_btn.setProperty("role", "ghost")
        self.add_cat_btn.clicked.connect(self._on_add_category)
        left_layout.addWidget(self.add_cat_btn)

        self.lock_btn = QPushButton("  Kilitle")
        self.lock_btn.setIcon(icons.lock_icon(16))
        self.lock_btn.setProperty("role", "danger")
        self.lock_btn.clicked.connect(self._on_lock)
        left_layout.addWidget(self.lock_btn)

        # Sağ panel
        right = QVBoxLayout()
        right.setSpacing(8)

        top_bar = QHBoxLayout()
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Ara — uygulama veya kullanıcı adı")
        self.search_edit.textChanged.connect(self._on_search_changed)

        self.new_btn = QPushButton("  Yeni Kayıt")
        self.new_btn.setIcon(icons.plus_icon(16))
        self.new_btn.setProperty("role", "primary")
        self.new_btn.clicked.connect(self._on_new_entry)

        top_bar.addWidget(self.search_edit, 1)
        top_bar.addWidget(self.new_btn)
        right.addLayout(top_bar)

        # Kolon başlık satırı — kartlardakiyle aynı stretch
        right.addWidget(self._build_header())

        # Kart akışı: scroll alanında dikey EntryCard listesi
        self.cards_container = QWidget()
        self.cards_layout = QVBoxLayout(self.cards_container)
        self.cards_layout.setContentsMargins(0, 0, 0, 0)
        self.cards_layout.setSpacing(6)
        self.cards_layout.addStretch(1)

        self.entry_scroll = QScrollArea()
        self.entry_scroll.setWidgetResizable(True)
        self.entry_scroll.setWidget(self.cards_container)
        self.entry_scroll.setFrameShape(QFrame.NoFrame)

        self._cards: dict[int, EntryCard] = {}

        self.empty_state = self._build_empty_state()

        self.list_stack = QStackedWidget()
        self.list_stack.addWidget(self.entry_scroll)  # index 0
        self.list_stack.addWidget(self.empty_state)   # index 1
        right.addWidget(self.list_stack, 1)

        root.addWidget(left)
        root.addLayout(right, 1)

        # Status bar
        self.status = QStatusBar()
        self.setStatusBar(self.status)
        self.lock_status_label = QLabel()
        self.status.addPermanentWidget(self.lock_status_label)

    def _apply_header_style(self, header: QFrame) -> None:
        c = theme.palette()
        header.setStyleSheet(f"""
            QFrame#ColumnHeader {{
                background: transparent;
                border-bottom: 1px solid {c['border']};
            }}
            QFrame#ColumnHeader QLabel {{
                color: {c['text_muted']};
                font-size: 11px;
                font-weight: 600;
                letter-spacing: 0.5px;
                text-transform: uppercase;
            }}
        """)

    def _build_header(self) -> QWidget:
        """Kolon başlıkları — EntryCard ile aynı genişlik şablonu."""
        header = QFrame()
        header.setObjectName("ColumnHeader")
        self._apply_header_style(header)
        self._header_widget = header
        row = QHBoxLayout(header)
        row.setContentsMargins(12, 6, 12, 6)
        row.setSpacing(10)

        # Boş yıldız kolonu için yer tutucu
        spacer = QLabel(" ")
        spacer.setFixedWidth(COL_FAV_W)
        row.addWidget(spacer)

        app_l = QLabel("Uygulama")
        app_l.setContentsMargins(4, 0, 0, 0)
        row.addWidget(app_l, COL_APP_STR)

        user_l = QLabel("Kullanıcı Adı")
        row.addWidget(user_l, COL_USER_STR)

        pw_l = QLabel("Şifre")
        row.addWidget(pw_l, COL_PW_STR)

        # Aksiyon kolonları — sağa hizalı tek "Eylemler" etiketi
        actions_l = QLabel("Eylemler")
        actions_l.setAlignment(Qt.AlignCenter)
        actions_l.setFixedWidth(COL_ACTION_W * 3 + 20)
        row.addWidget(actions_l)
        return header

    def _build_empty_state(self) -> QWidget:
        frame = QFrame()
        frame.setObjectName("Panel")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(10)
        layout.setAlignment(Qt.AlignCenter)

        self.empty_title = QLabel("Burası şimdilik boş")
        self.empty_title.setProperty("role", "title")
        self.empty_title.setAlignment(Qt.AlignCenter)

        self.empty_subtitle = QLabel(
            "İlk kaydını eklemek için aşağıdaki butona bas veya Ctrl+N kısayolunu kullan."
        )
        self.empty_subtitle.setProperty("role", "muted")
        self.empty_subtitle.setAlignment(Qt.AlignCenter)
        self.empty_subtitle.setWordWrap(True)

        cta = QPushButton("+ Yeni Kayıt Ekle")
        cta.setProperty("role", "primary")
        cta.clicked.connect(self._on_new_entry)

        layout.addStretch()
        layout.addWidget(self.empty_title)
        layout.addWidget(self.empty_subtitle)
        layout.addSpacing(8)
        layout.addWidget(cta, alignment=Qt.AlignCenter)
        layout.addStretch()
        return frame

    def _update_empty_state(self, total_rows: int) -> None:
        """Liste boşsa, neden boş olduğunu söylemek için metin değişir."""
        if total_rows > 0:
            self.list_stack.setCurrentIndex(0)
            return

        if self._search_text:
            self.empty_title.setText("Sonuç yok")
            self.empty_subtitle.setText(
                f"'{self._search_text}' aramasıyla eşleşen kayıt bulunamadı."
            )
        elif self._favorites_only:
            self.empty_title.setText("Favori yok")
            self.empty_subtitle.setText(
                "Bir kaydın bağlam menüsünden favori olarak işaretleyebilirsin."
            )
        elif self._current_category is not None:
            self.empty_title.setText("Bu kategori boş")
            self.empty_subtitle.setText("Buraya yeni bir kayıt ekleyebilirsin.")
        else:
            self.empty_title.setText("Burası şimdilik boş")
            self.empty_subtitle.setText(
                "İlk kaydını eklemek için aşağıdaki butona bas veya Ctrl+N kısayolunu kullan."
            )
        self.list_stack.setCurrentIndex(1)

    # ---------- menu ----------

    def _build_menu(self) -> None:
        menubar = self.menuBar()

        file_menu = menubar.addMenu("&Dosya")
        act_settings = QAction("Ayarlar…", self)
        act_settings.setShortcut(QKeySequence("Ctrl+,"))
        act_settings.triggered.connect(self._on_open_settings)
        file_menu.addAction(act_settings)

        file_menu.addSeparator()
        act_import = QAction("CSV İçe Aktar…", self)
        act_import.triggered.connect(self._on_import_csv)
        file_menu.addAction(act_import)

        act_export = QAction("CSV Dışa Aktar…", self)
        act_export.triggered.connect(self._on_export_csv)
        file_menu.addAction(act_export)

        file_menu.addSeparator()
        act_lock = QAction("Kilitle", self)
        act_lock.setShortcut(QKeySequence("Ctrl+L"))
        act_lock.triggered.connect(self._on_lock)
        file_menu.addAction(act_lock)

        act_quit = QAction("Çıkış", self)
        act_quit.setShortcut(QKeySequence("Ctrl+Q"))
        act_quit.triggered.connect(self.close)
        file_menu.addAction(act_quit)

        entry_menu = menubar.addMenu("&Kayıt")
        act_new = QAction("Yeni Kayıt", self)
        act_new.setShortcut(QKeySequence("Ctrl+N"))
        act_new.triggered.connect(self._on_new_entry)
        entry_menu.addAction(act_new)

        tools_menu = menubar.addMenu("&Araçlar")
        act_gen = QAction("Şifre Üreteci", self)
        act_gen.setShortcut(QKeySequence("Ctrl+G"))
        act_gen.triggered.connect(self._on_open_generator)
        tools_menu.addAction(act_gen)

        help_menu = menubar.addMenu("&Yardım")
        act_about = QAction("Hakkında", self)
        act_about.triggered.connect(self._on_open_about)
        help_menu.addAction(act_about)

    # ---------- auto-lock ----------

    def _setup_auto_lock(self) -> None:
        minutes = self.vault.get_auto_lock_minutes()
        self._auto_lock_seconds_total = minutes * 60
        self._remaining = self._auto_lock_seconds_total

        self._tick_timer = QTimer(self)
        self._tick_timer.setInterval(COUNTDOWN_TICK_MS)
        self._tick_timer.timeout.connect(self._on_tick)
        self._tick_timer.start()

        # Aktivite tespiti — global event filter
        from PySide6.QtWidgets import QApplication
        QApplication.instance().installEventFilter(self)
        self._update_lock_label()

    def eventFilter(self, obj, event):
        if event.type() in (
            QEvent.MouseMove, QEvent.MouseButtonPress, QEvent.KeyPress,
            QEvent.Wheel, QEvent.TouchBegin,
        ):
            self._remaining = self._auto_lock_seconds_total
        return super().eventFilter(obj, event)

    def _on_tick(self) -> None:
        self._remaining -= 1
        if self._remaining <= 0:
            self._on_lock()
            return
        self._update_lock_label()

    def _update_lock_label(self) -> None:
        m, s = divmod(self._remaining, 60)
        self.lock_status_label.setText(f"Auto-lock: {m:02d}:{s:02d}")

    # ---------- data reload ----------

    def _reload_categories(self) -> None:
        self.category_list.clear()
        for cat in self.vault.db.list_categories():
            item = QListWidgetItem(cat["name"])
            item.setData(Qt.UserRole, cat["id"])
            self.category_list.addItem(item)

    def _clear_cards(self) -> None:
        """cards_layout içindeki tüm kartları kaldırır, son stretch'i bırakır."""
        # Stretch en sondaki item — onun haricindekileri sil.
        while self.cards_layout.count() > 1:
            item = self.cards_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
        self._cards.clear()

    def _reload_entries(self) -> None:
        self._clear_cards()
        rows = self.vault.db.list_entries(
            category_id=self._current_category,
            favorites_only=self._favorites_only,
            search=self._search_text or None,
        )
        for row in rows:
            card = EntryCard(
                entry_id=row["id"],
                app_name=row["app_name"],
                username=row["username"],
                favorite=bool(row["favorite"]),
                parent=self.cards_container,
            )
            card.reveal_requested.connect(self._on_card_reveal)
            card.copy_username_requested.connect(self._on_card_copy_user)
            card.copy_password_requested.connect(self._on_card_copy_pw)
            card.history_requested.connect(self._on_card_history)
            card.edit_requested.connect(self._on_card_edit)
            card.favorite_requested.connect(self._on_card_favorite)
            card.delete_requested.connect(self._on_card_delete)

            self.cards_layout.insertWidget(self.cards_layout.count() - 1, card)
            self._cards[row["id"]] = card

        self.status.showMessage(f"{len(rows)} kayıt")
        self._update_empty_state(len(rows))

    # ---------- filters ----------

    def _set_filter(self, category_id: Optional[int], favorites_only: bool) -> None:
        self._current_category = category_id
        self._favorites_only = favorites_only
        self.category_list.clearSelection()
        self._reload_entries()

    def _on_category_clicked(self, item: QListWidgetItem) -> None:
        self._current_category = item.data(Qt.UserRole)
        self._favorites_only = False
        self._reload_entries()

    def _on_search_changed(self, text: str) -> None:
        self._search_text = text.strip()
        self._reload_entries()

    # ---------- categories ----------

    def _on_add_category(self) -> None:
        name, ok = QInputDialog.getText(self, "Yeni Kategori", "Kategori adı:")
        if not ok or not name.strip():
            return
        try:
            self.vault.db.add_category(name.strip())
        except Exception as exc:
            QMessageBox.warning(self, "Hata", str(exc))
            return
        self._reload_categories()

    def _on_category_context(self, pos) -> None:
        item = self.category_list.itemAt(pos)
        if not item:
            return
        category_id = item.data(Qt.UserRole)
        menu = QMenu(self)
        rename = menu.addAction("Yeniden adlandır")
        delete = menu.addAction("Sil")
        chosen = menu.exec(self.category_list.mapToGlobal(pos))
        if chosen == rename:
            new_name, ok = QInputDialog.getText(
                self, "Yeniden adlandır", "Yeni ad:", text=item.text()
            )
            if ok and new_name.strip():
                self.vault.db.rename_category(category_id, new_name.strip())
                self._reload_categories()
        elif chosen == delete:
            confirm = QMessageBox.question(
                self, "Sil",
                f"'{item.text()}' silinsin mi? Kayıtlar 'kategorisiz' olur."
            )
            if confirm == QMessageBox.Yes:
                self.vault.db.delete_category(category_id)
                self._reload_categories()
                self._reload_entries()

    # ---------- entries ----------

    def _on_new_entry(self) -> None:
        dialog = EntryDialog(self.vault, parent=self)
        if dialog.exec() != EntryDialog.Accepted:
            return
        try:
            self.vault.add_entry(dialog.get_entry())
        except Exception as exc:
            QMessageBox.critical(self, "Hata", f"Kayıt eklenemedi: {exc}")
            return
        self._reload_entries()

    # ---------- card signal handlers ----------

    def _on_card_reveal(self, entry_id: int) -> None:
        card = self._cards.get(entry_id)
        if card is None:
            return
        try:
            plain = self.vault.reveal_password(entry_id)
        except Exception as exc:
            QMessageBox.critical(self, "Hata", f"Şifre çözülemedi: {exc}")
            return
        card.show_password(plain)
        self.status.showMessage("Şifre 10 saniye sonra otomatik gizlenir.", 4000)

    def _on_card_copy_user(self, entry_id: int) -> None:
        row = self.vault.db.get_entry(entry_id)
        if not row:
            return
        copy_to_clipboard(row["username"])
        self.status.showMessage("Kullanıcı adı panoya kopyalandı.", 5000)

    def _on_card_copy_pw(self, entry_id: int) -> None:
        try:
            copy_to_clipboard(self.vault.reveal_password(entry_id))
        except Exception as exc:
            QMessageBox.critical(self, "Hata", str(exc))
            return
        self.status.showMessage("Şifre 20 saniyeliğine panoya kopyalandı.", 5000)

    def _on_card_history(self, entry_id: int) -> None:
        row = self.vault.db.get_entry(entry_id)
        if row:
            HistoryDialog(self.vault, entry_id, row["app_name"], parent=self).exec()

    def _on_card_edit(self, entry_id: int) -> None:
        row = self.vault.db.get_entry(entry_id)
        if row is None:
            return
        try:
            plain_pw = self.vault.decrypt(row["encrypted_password"])
        except Exception as exc:
            QMessageBox.critical(self, "Hata", f"Şifre çözülemedi: {exc}")
            return

        current = VaultEntry(
            id=row["id"],
            app_name=row["app_name"],
            username=row["username"],
            password=plain_pw,
            notes=row["notes"],
            category_id=row["category_id"],
            favorite=bool(row["favorite"]),
        )
        dialog = EntryDialog(self.vault, entry=current, parent=self)
        if dialog.exec() != EntryDialog.Accepted:
            return
        try:
            self.vault.update_entry(dialog.get_entry())
        except Exception as exc:
            QMessageBox.critical(self, "Hata", f"Güncelleme başarısız: {exc}")
            return
        self._reload_entries()

    def _on_card_favorite(self, entry_id: int) -> None:
        self.vault.db.toggle_favorite(entry_id)
        self._reload_entries()

    def _on_card_delete(self, entry_id: int) -> None:
        row = self.vault.db.get_entry(entry_id)
        name = row["app_name"] if row else ""
        confirm = QMessageBox.question(
            self, "Sil",
            f"'{name}' silinsin mi? Bu işlem geri alınamaz.",
        )
        if confirm == QMessageBox.Yes:
            self.vault.db.delete_entry(entry_id)
            self._reload_entries()

    # ---------- tools / help ----------

    def _on_open_generator(self) -> None:
        GeneratorDialog(parent=self).exec()

    def _on_open_about(self) -> None:
        AboutDialog(parent=self).exec()

    # ---------- settings ----------

    def _on_open_settings(self) -> None:
        dialog = SettingsDialog(self.vault, parent=self)
        dialog.settings_changed.connect(self._refresh_auto_lock)
        dialog.theme_changed.connect(self.apply_theme)
        dialog.exec()

    def _refresh_auto_lock(self) -> None:
        self._auto_lock_seconds_total = self.vault.get_auto_lock_minutes() * 60
        self._remaining = self._auto_lock_seconds_total
        self._update_lock_label()

    # ---------- theme ----------

    def apply_theme(self, name: str) -> None:
        """Tema değiştir — stylesheet'i, ikonları ve kartları yenile."""
        from PySide6.QtWidgets import QApplication
        theme.set_active(name)
        icons.clear_cache()
        QApplication.instance().setStyleSheet(theme.stylesheet())
        # Header inline stilini tema renklerine yeniden uygula
        if hasattr(self, "_header_widget"):
            self._apply_header_style(self._header_widget)
        # Toolbar/sidebar buton ikonları
        self.new_btn.setIcon(icons.plus_icon(16))
        self.lock_btn.setIcon(icons.lock_icon(16))
        # Kartlar — yeniden inşa ederek temayı al
        self._reload_entries()

    # ---------- csv ----------

    def _on_export_csv(self) -> None:
        from PySide6.QtWidgets import QFileDialog
        confirm = QMessageBox.warning(
            self, "Düz metin dışa aktarım",
            "Bu işlem TÜM şifreleri DÜZ METİN olarak diske yazacak. "
            "Devam etmek istediğine emin misin?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if confirm != QMessageBox.Yes:
            return

        pw, ok = QInputDialog.getText(
            self, "Master password",
            "Devam etmek için master password'ünü tekrar gir:",
            echo=QLineEdit.Password,
        )
        if not ok:
            return
        if not self.vault.verify_current_password(pw):
            QMessageBox.warning(self, "Hatalı", "Master password yanlış. Dışa aktarım iptal edildi.")
            return

        path, _ = QFileDialog.getSaveFileName(
            self, "CSV olarak kaydet", "keyora-export.csv", "CSV (*.csv)"
        )
        if not path:
            return

        try:
            count = csv_io.export_csv(self.vault, path)
        except Exception as exc:
            QMessageBox.critical(self, "Hata", f"Dışa aktarım başarısız: {exc}")
            return
        QMessageBox.information(self, "Tamam", f"{count} kayıt dışa aktarıldı.")

    def _on_import_csv(self) -> None:
        from PySide6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getOpenFileName(
            self, "CSV dosyası seç", "", "CSV (*.csv)"
        )
        if not path:
            return

        try:
            count = csv_io.import_csv(self.vault, path)
        except Exception as exc:
            QMessageBox.critical(self, "Hata", f"İçe aktarım başarısız: {exc}")
            return
        self._reload_categories()
        self._reload_entries()
        QMessageBox.information(self, "Tamam", f"{count} kayıt içe aktarıldı.")

    # ---------- lock ----------

    def _on_lock(self) -> None:
        self._tick_timer.stop()
        self.vault.lock()
        self.close()
