"""
Design system for Blog Compiler.

Two flat themes over one QSS template:

- LIGHT — 亮白：纯白画布 + 浅灰面板 + 钴蓝强调
- DARK  — 黑蓝：偏蓝的深底 + 冷灰字 + 亮蓝强调

两套色板共用同一组键名，`build_stylesheet(theme)` 只换字典不复制样式表。
`grad` / `grad_hover` 存的是**纯色**（早期版本是渐变，已被替换），
保留键名是为了模板不用改。

关于「质感」：Qt 样式表**不支持 box-shadow**，所以层次只能靠三件事做出来——
底色明度差、细边框、以及 `qlineargradient` 的极淡渐变。
`surface_*` 这组 token 就是为此存在的：越靠上的表面越亮。
"""

from string import Template


def _rgba(hex_color: str, alpha: float) -> str:
    """把 #RRGGBB 转成 rgba()，QSS 的渐变需要用带透明度的颜色。"""
    value = hex_color.lstrip("#")
    r, g, b = (int(value[i:i + 2], 16) for i in (0, 2, 4))
    return f"rgba({r}, {g}, {b}, {alpha:.2f})"


def _sheen(base: str, top_alpha: float, bottom_alpha: float) -> str:
    """用同一色相的两层极淡叠加做「光泽」，模拟出一点厚度。

    顶部略亮、底部略暗，视觉上就像有一层柔和的高光——
    这是 QSS 里最接近 box-shadow 的做法。
    """
    return (
        "qlineargradient(x1:0, y1:0, x2:0, y2:1, "
        f"stop:0 {_rgba(base, top_alpha)}, stop:1 {_rgba(base, bottom_alpha)})"
    )


#: 强调色。两套主题共用同一个蓝，保证品牌一致
ACCENT = "#4C7DFF"
ACCENT_HOVER = "#6A93FF"
ACCENT_PRESSED = "#3A66E0"

#: 深色主题用更亮的蓝，否则在深底上发闷
ACCENT_DARK = "#3B82F6"
ACCENT_DARK_HOVER = "#5B9AFF"
ACCENT_DARK_PRESSED = "#2C6BD8"

#: 亮色主题的悬停态要比常态更深（白底上提亮会糊）
ACCENT_LIGHT_HOVER = "#3A66E0"
ACCENT_LIGHT_PRESSED = "#2C4FB8"

#: 白色光泽 / 黑色阴影，两套主题共用
_WHITE = "#FFFFFF"
_BLACK = "#000000"


DARK = {
    # 画布最深，越往上越亮 —— 这是层次感的来源
    "bg_base": "#080C12",
    "bg_panel": "#0F1620",
    "bg_card": "#151E2B",
    "bg_input": "#131C27",
    "bg_hover": "#1C2735",
    "border": "#1F2B3A",
    "border_strong": "#314054",
    "text_primary": "#E9F0F8",
    "text_secondary": "#93A4B8",
    "text_muted": "#8593A7",
    "accent": ACCENT_DARK,
    "accent2": "#2C6BD8",
    "accent_hover": ACCENT_DARK_HOVER,
    "accent_pressed": ACCENT_DARK_PRESSED,
    "accent_soft": "#16233A",
    "success": "#25C07A",
    "warning": "#E0A93B",
    "danger": "#F0705F",
    "info": "#58B4F5",
    "grad": ACCENT_DARK,
    "grad_hover": ACCENT_DARK_HOVER,
    "radius_sm": "8px",
    "radius_md": "10px",
    "radius_lg": "14px",
    "scroll_track": "#080C12",
    "scroll_handle": "#243244",
    "scroll_handle_hover": "#33445B",
    "splitter": "#16212E",
    # 质感：白色光泽（暗色主题靠提亮，但强度要克制，否则顶部栏会发白）
    "sheen": _sheen(_WHITE, 0.028, 0.0),
    "sheen_strong": _sheen(_WHITE, 0.055, 0.0),
    # 编辑区是「纸」，必须比按钮/卡片暗，否则并排的正文和按钮糊成一片
    "card_grad": "qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #1A2534, stop:1 #141D29)",
    "input_grad": "qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #0C121A, stop:1 #101822)",
    "accent_grad": f"qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #4A8CFA, stop:1 {ACCENT_DARK})",
    "accent_grad_hover": f"qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #6BA6FF, stop:1 {ACCENT_DARK_HOVER})",
}

LIGHT = {
    # 亮色主题里「画布」是最亮的，面板靠边框和极浅灰区分
    # （bg_base 不能压太暗，否则正文对底色的对比度达不到 AAA）
    "bg_base": "#FFFFFF",
    "bg_panel": "#FFFFFF",
    "bg_card": "#F6F8FB",
    "bg_input": "#F4F6FA",
    "bg_hover": "#EDF1F7",
    "border": "#E2E8F0",
    "border_strong": "#C7D2E0",
    "text_primary": "#0B1220",
    "text_secondary": "#46536A",
    "text_muted": "#63718A",
    "accent": ACCENT,
    "accent2": "#3A66E0",
    "accent_hover": ACCENT_LIGHT_HOVER,
    "accent_pressed": ACCENT_LIGHT_PRESSED,
    "accent_soft": "#EDF3FF",
    "success": "#12915A",
    "warning": "#B7791F",
    "danger": "#D64545",
    "info": "#1F7AE0",
    "grad": ACCENT,
    "grad_hover": ACCENT_LIGHT_HOVER,
    "radius_sm": "8px",
    "radius_md": "10px",
    "radius_lg": "14px",
    "scroll_track": "#F5F7FA",
    "scroll_handle": "#CFD8E3",
    "scroll_handle_hover": "#A9B6C6",
    "splitter": "#E2E8F0",
    # 质感：亮色主题靠把按钮/卡片压成浅灰，与白色面板拉开
    "sheen": "qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #FFFFFF, stop:1 #FBFCFE)",
    "sheen_strong": "qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #FFFFFF, stop:1 #EDF2F8)",
    "card_grad": "qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #FCFDFE, stop:1 #EEF2F7)",
    "input_grad": "qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #FDFEFF, stop:1 #F7F9FC)",
    "accent_grad": f"qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #5C89FF, stop:1 {ACCENT})",
    "accent_grad_hover": f"qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #7398FF, stop:1 {ACCENT_LIGHT_HOVER})",
}


_TEMPLATE = Template("""
    * {
        font-family: "Inter", "Microsoft YaHei UI", "Segoe UI", sans-serif;
    }
    /* 层次：画布(bg_base) < 面板(bg_panel) < 卡片(bg_card) < 悬停(bg_hover)。
       越是「浮在上面」的表面越亮，这样不依赖 box-shadow（QSS 不支持）也能分层。 */
    QMainWindow, QWidget#rightPanel {
        background-color: $bg_base;
        color: $text_primary;
    }
    QWidget {
        background-color: transparent;
        color: $text_primary;
        font-size: 13px;
    }
    /* QWidget 默认透明，露出的底色来自父控件。下面这些「容器」控件
       如果不显式给背景，Qt 会用自己的原生亮色——暗色主题下会露出一条白边。 */
    QTabWidget, QTabWidget::pane {
        background-color: $bg_base;
        border: none;
    }
    QStackedWidget {
        background-color: $bg_panel;
        border: none;
    }
    QStackedWidget#fileStack {
        background-color: $bg_panel;
    }
    QSplitter {
        background-color: $bg_base;
    }

    QFrame#commandBar {
        background: $sheen;
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
        background: $sheen;
        border-right: 1px solid $border;
    }
    QPushButton#railBtn {
        background-color: transparent;
        border: 1px solid transparent;
        border-radius: $radius_sm;
        padding: 8px;
        min-width: 36px;
        min-height: 36px;
    }
    QPushButton#railBtn:hover {
        background-color: $bg_hover;
        border-color: $border;
    }
    QPushButton#railBtn:checked {
        background-color: $accent_soft;
        border-color: $accent;
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
        background: $card_grad;
        border: 1px solid $border;
        border-radius: $radius_lg;
    }
    QFrame#resultRow {
        background: $input_grad;
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
        background: $accent_grad;
        color: #FFFFFF;
        border: 1px solid $accent_pressed;
        border-radius: $radius_sm;
        padding: 8px 16px;
        font-size: 13px;
        font-weight: 600;
    }
    QPushButton#primaryBtn:hover {
        background: $accent_grad_hover;
    }
    QPushButton#primaryBtn:pressed {
        background: $accent_pressed;
    }
    QPushButton#primaryBtn:disabled {
        background: $bg_hover;
        border-color: $border;
        color: $text_muted;
    }
    QPushButton#secondaryBtn {
        background: $card_grad;
        color: $text_primary;
        border: 1px solid $border_strong;
        border-radius: $radius_sm;
        padding: 7px 16px;
        font-size: 13px;
        font-weight: 500;
    }
    QPushButton#secondaryBtn:hover {
        background: $sheen_strong;
        border-color: $accent;
    }
    QPushButton#secondaryBtn:pressed {
        background-color: $bg_card;
    }
    QPushButton#secondaryBtn:disabled {
        background: transparent;
        color: $text_muted;
        border-color: $border;
    }
    QPushButton#draftBtn {
        background: $card_grad;
        color: $text_secondary;
        border: 1px solid $border_strong;
        border-radius: $radius_sm;
        padding: 5px 11px;
        font-size: 11.5px;
        min-width: 40px;
    }
    QPushButton#draftBtn:hover {
        background-color: $bg_hover;
        color: $text_primary;
        border-color: $accent;
    }
    QPushButton#draftBtn:disabled {
        background: transparent;
        color: $text_muted;
        border-color: $border;
    }
    /* 并排面板的标题条（原文 / 改写后 / 预览） */
    QFrame#panelHeader {
        background-color: $bg_panel;
        border-bottom: 1px solid $border;
    }
    QLabel#panelTitle {
        color: $text_secondary;
        font-size: 12px;
        font-weight: 600;
    }
    QLabel#panelTitle_rewritten {
        color: $accent;
        font-size: 12px;
        font-weight: 600;
    }
    QLabel#panelCounter {
        color: $text_muted;
        font-size: 11.5px;
    }
    QWidget#panel_original, QWidget#panel_rewritten, QWidget#panel_preview,
    QSplitter#compare {
        background-color: $bg_base;
    }

    /* 顶部四步导航 */
    QFrame#stepper {
        background: $sheen;
        border-bottom: 1px solid $border;
    }
    QLabel#stepArrow {
        color: $border_strong;
        font-size: 15px;
    }
    QPushButton#stepCard {
        background: $card_grad;
        border: 1px solid $border;
        border-radius: $radius_md;
        text-align: left;
    }
    QPushButton#stepCard:hover {
        background: $sheen_strong;
        border-color: $border_strong;
    }
    QPushButton#stepCard:checked {
        background: $accent_soft;
        border: 1px solid $accent;
    }
    QLabel#stepBadge {
        background-color: $bg_hover;
        color: $text_muted;
        border-radius: 12px;
        font-size: 12px;
        font-weight: 700;
    }
    QLabel#stepBadge[state="done"] {
        background-color: $success;
        color: #FFFFFF;
    }
    QLabel#stepName {
        color: $text_primary;
        font-size: 13px;
        font-weight: 600;
    }
    QLabel#stepHint {
        color: $text_muted;
        font-size: 11px;
    }

    /* 左侧任务面板 */
    QStackedWidget#taskPanel, QWidget#taskPage {
        background-color: $bg_panel;
        border-left: 1px solid $border;
    }
    QLabel#taskTitle {
        color: $text_primary;
        font-size: 15px;
        font-weight: 650;
    }
    QLabel#taskDesc {
        color: $text_muted;
        font-size: 12.5px;
    }
    QLabel#taskLabel {
        color: $text_secondary;
        font-size: 12px;
        font-weight: 600;
    }
    QLabel#statBlock {
        background: $card_grad;
        border: 1px solid $border;
        border-radius: $radius_md;
        color: $text_secondary;
        font-size: 12.5px;
        padding: 10px 12px;
    }
    QLabel#statDetail {
        color: $text_muted;
        font-size: 12px;
    }

    /* 底部常驻操作栏 */
    QFrame#actionBar {
        background: $sheen;
        border-top: 1px solid $border;
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
        border: 1px solid transparent;
    }
    QListWidget::item:selected {
        background: $accent_soft;
        color: $text_primary;
        border-color: $accent;
    }
    QListWidget::item:hover:!selected {
        background-color: $bg_hover;
        border-color: $border;
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
    }    QLabel#emptyState {
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
    /* 正文面板：画布底色 + 顶部一条极淡光泽，读起来像一张「纸」而不是色块 */
    QTextEdit#editor, QTextBrowser#previewRender {
        background: $input_grad;
        border: none;
        border-radius: 0px;
        padding: 16px 18px;
    }
    QTextEdit#logView {
        background-color: $bg_base;
        border: 1px solid $border;
        border-radius: $radius_sm;
        font-size: 11.5px;
        padding: 6px;
    }
    QLabel#previewStats {
        background: $card_grad;
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
