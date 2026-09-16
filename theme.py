"""
Design system for Blog Compiler.

Dark-first token palette with an indigo->cyan gradient accent.
`build_stylesheet(tokens)` renders a single QSS template so the whole app
can be re-themed by swapping token dicts instead of duplicating stylesheets.
"""

from string import Template


ACCENT_GRADIENT = "qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #4F46E5, stop:1 #0891B2)"
ACCENT_GRADIENT_HOVER = "qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #6366F1, stop:1 #06B6D4)"


DARK = {
    "bg_base": "#0B0F14",
    "bg_panel": "#111827",
    "bg_card": "#151C26",
    "bg_input": "#0F1520",
    "bg_hover": "#1C2530",
    "border": "#243040",
    "border_strong": "#334155",
    "text_primary": "#E6EDF3",
    "text_secondary": "#9AA7B4",
    "text_muted": "#7C8B9E",
    "accent": "#06B6D4",
    "accent2": "#4F46E5",
    "accent_hover": "#22D3EE",
    "accent_pressed": "#0891B2",
    "accent_soft": "#0C2B33",
    "success": "#22C55E",
    "warning": "#F59E0B",
    "danger": "#EF4444",
    "info": "#38BDF8",
    "grad": ACCENT_GRADIENT,
    "grad_hover": ACCENT_GRADIENT_HOVER,
    "radius_sm": "6px",
    "radius_md": "10px",
    "radius_lg": "14px",
    "scroll_track": "#0B0F14",
    "scroll_handle": "#2A3644",
    "scroll_handle_hover": "#3E4C5E",
    "splitter": "#1A222E",
}

LIGHT = {
    "bg_base": "#F6F8FB",
    "bg_panel": "#FFFFFF",
    "bg_card": "#FFFFFF",
    "bg_input": "#FFFFFF",
    "bg_hover": "#EEF2F7",
    "border": "#E2E8F0",
    "border_strong": "#CBD5E1",
    "text_primary": "#1E293B",
    "text_secondary": "#475569",
    "text_muted": "#64748B",
    "accent": "#0891B2",
    "accent2": "#4F46E5",
    "accent_hover": "#0E7490",
    "accent_pressed": "#155E75",
    "accent_soft": "#E0F7FA",
    "success": "#16A34A",
    "warning": "#D97706",
    "danger": "#DC2626",
    "info": "#0284C7",
    "grad": ACCENT_GRADIENT,
    "grad_hover": "qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #6366F1, stop:1 #0891B2)",
    "radius_sm": "6px",
    "radius_md": "10px",
    "radius_lg": "14px",
    "scroll_track": "#F6F8FB",
    "scroll_handle": "#CBD5E1",
    "scroll_handle_hover": "#94A3B8",
    "splitter": "#E2E8F0",
}


_TEMPLATE = Template("""
    * {
        font-family: "Inter", "Microsoft YaHei UI", "Segoe UI", sans-serif;
    }
    QMainWindow, QWidget#rightPanel {
        background-color: $bg_base;
        color: $text_primary;
    }
    QWidget {
        background-color: transparent;
        color: $text_primary;
        font-size: 13px;
    }

    QFrame#commandBar {
        background-color: $bg_panel;
        border-bottom: 1px solid $border;
    }
    QLabel#barTitle {
        font-size: 14px;
        font-weight: 600;
        color: $text_primary;
        letter-spacing: 0.3px;
    }
    QPushButton#cmdBtn {
        background-color: transparent;
        color: $text_secondary;
        border: none;
        padding: 6px 12px;
        border-radius: $radius_sm;
        font-size: 13px;
    }
    QPushButton#cmdBtn:hover {
        background-color: $bg_hover;
        color: $text_primary;
    }
    QPushButton#cmdIconBtn {
        background-color: transparent;
        color: $text_secondary;
        border: none;
        border-radius: $radius_sm;
        padding: 6px;
        min-width: 32px;
        min-height: 32px;
    }
    QPushButton#cmdIconBtn:hover {
        background-color: $bg_hover;
        color: $text_primary;
    }
    QPushButton#cmdIconBtn:checked {
        background-color: $accent_soft;
        color: $accent;
    }
    QFrame#navRail {
        background-color: $bg_panel;
        border-right: 1px solid $border;
    }
    QPushButton#railBtn {
        background-color: transparent;
        border: none;
        border-radius: $radius_sm;
        padding: 8px;
        min-width: 36px;
        min-height: 36px;
    }
    QPushButton#railBtn:hover {
        background-color: $bg_hover;
    }
    QPushButton#railBtn:checked {
        background-color: $accent_soft;
    }
    QLabel#breadcrumb {
        color: $text_muted;
        font-size: 12px;
    }
    QLineEdit#fileSearch {
        background-color: $bg_input;
        border: 1px solid $border;
        border-radius: $radius_sm;
        padding: 4px 10px;
        font-size: 12px;
    }

    QFrame#card {
        background-color: $bg_card;
        border: 1px solid $border;
        border-radius: $radius_lg;
    }
    QFrame#resultRow {
        background-color: $bg_input;
        border: 1px solid $border;
        border-radius: $radius_sm;
    }
    QLabel#cardTitle {
        font-size: 12px;
        font-weight: 600;
        color: $text_muted;
        letter-spacing: 1px;
        padding-bottom: 4px;
    }
    QLabel#pubName {
        font-weight: 600;
        color: $text_primary;
    }

    QPushButton#primaryBtn {
        background: $grad;
        color: #FFFFFF;
        border: none;
        border-radius: $radius_sm;
        padding: 8px 16px;
        font-size: 13px;
        font-weight: 500;
    }
    QPushButton#primaryBtn:hover {
        background: $grad_hover;
    }
    QPushButton#primaryBtn:pressed {
        background-color: $accent_pressed;
    }
    QPushButton#primaryBtn:disabled {
        background: $bg_hover;
        color: $text_muted;
    }
    QPushButton#secondaryBtn {
        background-color: transparent;
        color: $text_primary;
        border: 1px solid $border_strong;
        border-radius: $radius_sm;
        padding: 7px 16px;
        font-size: 13px;
    }
    QPushButton#secondaryBtn:hover {
        background-color: $bg_hover;
        border-color: $accent;
    }
    QPushButton#secondaryBtn:disabled {
        color: $text_muted;
        border-color: $border;
    }
    QPushButton#draftBtn {
        background-color: transparent;
        color: $text_secondary;
        border: 1px solid $border_strong;
        border-radius: $radius_sm;
        padding: 4px 10px;
        font-size: 11px;
        min-width: 40px;
    }
    QPushButton#draftBtn:hover {
        background-color: $bg_hover;
        color: $text_primary;
    }
    QPushButton#draftBtn:disabled {
        color: $text_muted;
        border-color: $border;
    }

    QListWidget, QListWidget#fileList {
        background-color: $bg_panel;
        color: $text_primary;
        border: none;
        border-radius: 0px;
        outline: none;
    }
    QListWidget::item {
        padding: 8px 12px;
        border-radius: $radius_sm;
        margin: 2px 6px;
    }
    QListWidget::item:selected {
        background-color: $accent_soft;
        color: $text_primary;
    }
    QListWidget::item:hover:!selected {
        background-color: $bg_hover;
    }
    QListWidget#imageStatus {
        background-color: $bg_input;
        border: 1px solid $border;
        border-radius: $radius_md;
        font-size: 12px;
    }
    QListWidget#imageStatus::item {
        padding: 4px 8px;
        margin: 1px 4px;
        border-radius: 4px;
    }
    QStackedWidget#fileStack {
        background-color: $bg_panel;
        border: none;
    }
    QLabel#emptyState {
        color: $text_muted;
        font-size: 13px;
        padding: 24px;
        background-color: transparent;
    }
    QLabel#onboardTitle {
        font-size: 18px;
        font-weight: 600;
        color: $text_primary;
        padding-bottom: 8px;
    }

    QTextEdit, QTextBrowser {
        background-color: $bg_input;
        color: $text_primary;
        border: 1px solid $border;
        border-radius: $radius_md;
        padding: 10px;
    }
    QTextEdit#editor {
        border: 1px solid $border;
    }
    QTextEdit#logView {
        background-color: $bg_input;
        border: 1px solid $border;
        border-radius: $radius_md;
        font-size: 12px;
        padding: 6px;
    }
    QLabel#previewStats {
        background-color: $bg_input;
        border: 1px solid $border;
        border-radius: $radius_md;
        padding: 8px 12px;
        font-size: 12px;
        color: $text_secondary;
    }

    QTabWidget#contentTabs::pane {
        background-color: $bg_base;
        border: none;
        border-top: 1px solid $border;
    }
    QTabBar {
        qproperty-drawBase: 0;
    }
    QTabBar::tab {
        background-color: transparent;
        color: $text_muted;
        border: none;
        padding: 7px 18px;
        margin: 6px 2px;
        font-size: 13px;
        border-radius: $radius_sm;
    }
    QTabBar::tab:selected {
        color: $text_primary;
        background-color: $bg_hover;
    }
    QTabBar::tab:hover:!selected {
        color: $text_secondary;
        background-color: $bg_hover;
    }

    QComboBox, QComboBox#draftCombo {
        background-color: $bg_input;
        color: $text_primary;
        border: 1px solid $border_strong;
        border-radius: $radius_sm;
        padding: 6px 10px;
        font-size: 12px;
        min-height: 20px;
    }
    QComboBox:hover {
        border-color: $accent;
    }
    QComboBox::drop-down {
        border: none;
        width: 24px;
    }
    QComboBox::down-arrow {
        image: none;
        border-left: 5px solid transparent;
        border-right: 5px solid transparent;
        border-top: 5px solid $text_secondary;
        margin-right: 6px;
    }
    QComboBox QAbstractItemView {
        background-color: $bg_card;
        color: $text_primary;
        border: 1px solid $border;
        border-radius: $radius_sm;
        selection-background-color: $accent;
        selection-color: #FFFFFF;
        padding: 4px;
        outline: none;
    }

    QRadioButton {
        spacing: 8px;
        font-size: 12px;
        color: $text_secondary;
        padding: 4px 0;
    }
    QRadioButton::indicator {
        width: 16px;
        height: 16px;
        border-radius: 8px;
        border: 2px solid $border_strong;
        background-color: transparent;
    }
    QRadioButton::indicator:checked {
        border: 2px solid $accent;
        background-color: $accent;
    }
    QRadioButton::indicator:hover {
        border-color: $accent_hover;
    }

    QProgressBar#progressBar {
        background-color: $bg_hover;
        border: none;
        border-radius: 4px;
        text-align: center;
        color: #FFFFFF;
        font-size: 11px;
        height: 6px;
    }
    QProgressBar::chunk {
        background: $grad;
        border-radius: 4px;
    }

    QStatusBar#statusBar {
        background-color: $bg_panel;
        color: $text_secondary;
        font-size: 12px;
        padding: 2px 12px;
        border: none;
        border-top: 1px solid $border;
    }
    QStatusBar::item {
        border: none;
    }
    QLabel#statusLabel {
        color: $text_secondary;
        font-size: 12px;
    }

    QSplitter::handle {
        background-color: $splitter;
    }
    QSplitter::handle:horizontal {
        width: 1px;
    }

    QScrollBar:vertical {
        background-color: $scroll_track;
        width: 10px;
        margin: 0;
        border-radius: 5px;
    }
    QScrollBar::handle:vertical {
        background-color: $scroll_handle;
        border-radius: 5px;
        min-height: 30px;
    }
    QScrollBar::handle:vertical:hover {
        background-color: $scroll_handle_hover;
    }
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
        height: 0;
        background: none;
    }
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
        background: none;
    }
    QScrollBar:horizontal {
        background-color: $scroll_track;
        height: 10px;
        margin: 0;
        border-radius: 5px;
    }
    QScrollBar::handle:horizontal {
        background-color: $scroll_handle;
        border-radius: 5px;
        min-width: 30px;
    }
    QScrollBar::handle:horizontal:hover {
        background-color: $scroll_handle_hover;
    }
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
        width: 0;
        background: none;
    }
    QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {
        background: none;
    }

    QDialog {
        background-color: $bg_panel;
    }
    QGroupBox {
        border: 1px solid $border;
        border-radius: $radius_md;
        margin-top: 8px;
        padding-top: 16px;
        font-size: 13px;
        color: $text_secondary;
    }
    QGroupBox::title {
        subcontrol-origin: margin;
        left: 12px;
        padding: 0 6px;
    }
    QLineEdit {
        background-color: $bg_input;
        color: $text_primary;
        border: 1px solid $border_strong;
        border-radius: $radius_sm;
        padding: 6px 10px;
        font-size: 13px;
    }
    QLineEdit:focus {
        border-color: $accent;
    }
    QDoubleSpinBox, QSpinBox {
        background-color: $bg_input;
        color: $text_primary;
        border: 1px solid $border_strong;
        border-radius: $radius_sm;
        padding: 4px 8px;
        font-size: 13px;
    }
    QCheckBox {
        spacing: 8px;
        font-size: 13px;
        color: $text_primary;
    }
    QCheckBox::indicator {
        width: 16px;
        height: 16px;
        border-radius: 4px;
        border: 2px solid $border_strong;
        background-color: transparent;
    }
    QCheckBox::indicator:checked {
        background-color: $accent;
        border-color: $accent;
    }
    QCheckBox::indicator:hover {
        border-color: $accent_hover;
    }
    QDialogButtonBox QPushButton {
        background: $grad;
        color: #FFFFFF;
        border: none;
        border-radius: $radius_sm;
        padding: 8px 20px;
        font-size: 13px;
        min-width: 80px;
    }
    QDialogButtonBox QPushButton:hover {
        background: $grad_hover;
    }

    QMenu {
        background-color: $bg_card;
        color: $text_primary;
        border: 1px solid $border;
        border-radius: $radius_sm;
        padding: 4px;
    }
    QMenu::item {
        padding: 6px 20px;
        border-radius: 4px;
    }
    QMenu::item:selected {
        background-color: $accent_soft;
        color: $accent;
    }
    QToolTip {
        background-color: $bg_card;
        color: $text_primary;
        border: 1px solid $border;
        border-radius: 4px;
        padding: 4px 8px;
    }
""")


def get_tokens(theme: str = "dark") -> dict:
    return LIGHT if theme == "light" else DARK


def build_stylesheet(theme: str = "dark") -> str:
    return _TEMPLATE.substitute(get_tokens(theme))
