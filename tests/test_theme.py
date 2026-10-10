"""配色的可读性约束。

主题 token 是纯数据，但"看得清"是可以量化的：按 WCAG 相对亮度公式算对比度，
低于标准的组合直接判失败。这样以后调整配色时不会悄悄把文字改糊。
"""

import pytest

import theme as theme_module


def _relative_luminance(hex_color: str) -> float:
    value = hex_color.lstrip("#")
    if len(value) == 3:
        value = "".join(c * 2 for c in value)
    channels = [int(value[i:i + 2], 16) / 255 for i in (0, 2, 4)]

    def linearize(c):
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (linearize(c) for c in channels)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(fg: str, bg: str) -> float:
    a, b = _relative_luminance(fg), _relative_luminance(bg)
    lighter, darker = max(a, b), min(a, b)
    return (lighter + 0.05) / (darker + 0.05)


THEMES = {"light": theme_module.LIGHT, "dark": theme_module.DARK}


@pytest.fixture(params=sorted(THEMES))
def palette(request):
    return request.param, THEMES[request.param]


class TestContrast:
    def test_body_text_is_aaa(self, palette):
        name, t = palette
        ratio = contrast_ratio(t["text_primary"], t["bg_base"])
        assert ratio >= 7.0, f"{name} 正文对比度只有 {ratio:.1f}:1"

    def test_secondary_text_is_aaa(self, palette):
        name, t = palette
        ratio = contrast_ratio(t["text_secondary"], t["bg_base"])
        assert ratio >= 7.0, f"{name} 次要文字对比度只有 {ratio:.1f}:1"

    def test_muted_text_is_at_least_aa(self, palette):
        """muted 用于提示、占位符等非关键文字，AA 即可。"""
        name, t = palette
        ratio = contrast_ratio(t["text_muted"], t["bg_base"])
        assert ratio >= 4.5, f"{name} 弱化文字对比度只有 {ratio:.1f}:1"

    def test_accent_button_text_is_readable(self, palette):
        """主按钮是白字压在强调色上。"""
        name, t = palette
        ratio = contrast_ratio("#FFFFFF", t["accent"])
        assert ratio >= 3.5, f"{name} 主按钮文字对比度只有 {ratio:.1f}:1"

    def test_accent_is_visible_against_panels(self, palette):
        """按钮/强调元素相对面板底色要能分辨出来。"""
        name, t = palette
        ratio = contrast_ratio(t["accent"], t["bg_panel"])
        assert ratio >= 3.0, f"{name} 强调色相对面板只有 {ratio:.1f}:1"

    def test_borders_are_visible_but_not_loud(self, palette):
        name, t = palette
        ratio = contrast_ratio(t["border"], t["bg_panel"])
        assert 1.05 <= ratio <= 2.5, f"{name} 边框对比度 {ratio:.2f} 不合适"

    def test_danger_is_readable_as_text(self, palette):
        name, t = palette
        ratio = contrast_ratio(t["danger"], t["bg_panel"])
        assert ratio >= 3.0, f"{name} 危险色对比度只有 {ratio:.1f}:1"


class TestTokenContract:
    """模板靠这些键渲染；缺一个就会在界面上出现空样式。"""

    REQUIRED = [
        "bg_base", "bg_panel", "bg_card", "bg_input", "bg_hover",
        "border", "border_strong",
        "text_primary", "text_secondary", "text_muted",
        "accent", "accent_hover", "accent_pressed", "accent_soft",
        "success", "warning", "danger", "info",
        "grad", "grad_hover",
        "panel_original", "panel_rewritten", "panel_preview",
        "radius_sm", "radius_md", "radius_lg",
        "scroll_track", "scroll_handle", "scroll_handle_hover", "splitter",
    ]

    @pytest.mark.parametrize("name", sorted(THEMES))
    def test_every_required_token_exists(self, name):
        missing = [k for k in self.REQUIRED if k not in THEMES[name]]
        assert missing == [], f"{name} 缺少 token: {missing}"

    @pytest.mark.parametrize("name", sorted(THEMES))
    def test_colour_tokens_are_valid_hex(self, name):
        tokens = THEMES[name]
        for key in self.REQUIRED:
            if key.startswith("radius"):
                continue
            value = tokens[key]
            assert value.startswith("#") and len(value) == 7, f"{name}.{key}={value!r}"

    @pytest.mark.parametrize("name", sorted(THEMES))
    def test_no_gradients_remain(self, name):
        """早期版本用靛青→青色渐变，已被替换为扁平色。"""
        tokens = THEMES[name]
        for key in self.REQUIRED:
            assert "qlineargradient" not in str(tokens[key]), f"{name}.{key} 仍是渐变"


class TestStylesheet:
    @pytest.mark.parametrize("name", sorted(THEMES))
    def test_template_placeholders_are_all_filled(self, name):
        qss = theme_module.build_stylesheet(name)
        assert "$" not in qss, "仍有未被替换的占位符"

    @pytest.mark.parametrize("name", sorted(THEMES))
    def test_stylesheet_carries_the_accent(self, name):
        qss = theme_module.build_stylesheet(name)
        assert THEMES[name]["accent"] in qss

    @pytest.mark.parametrize("name", sorted(THEMES))
    def test_container_widgets_define_their_own_background(self, name):
        """模板把 QWidget 设成透明，靠父控件露底色。

        所以 QTabWidget / QStackedWidget / QSplitter 这些「容器」必须自己
        声明背景色；漏了就会露出 Qt 原生亮色——暗色主题下表现为一条白边。
        """
        qss = theme_module.build_stylesheet(name)
        import re

        for selector in ("QTabWidget", "QSplitter"):
            blocks = re.findall(r"([^{}]*)\{([^}]*)\}", qss)
            matched = [
                body for sel, body in blocks
                if selector in sel and "background-color" in body
            ]
            assert matched, f"{selector} 缺少 background-color 声明"

    def test_unknown_theme_falls_back_without_crashing(self):
        assert theme_module.build_stylesheet("nope") == theme_module.build_stylesheet("dark")

    def test_get_tokens_matches_the_dicts(self):
        assert theme_module.get_tokens("light") == theme_module.LIGHT
        assert theme_module.get_tokens("dark") == theme_module.DARK
