<div align="center">

# Blog Compiler

📝 Typora 笔记 → AI 改写 → 图片上传 → 一键发布 CSDN / 掘金 / 博客园

[![GitHub release](https://img.shields.io/github/v/release/200762zzy/Blog-Compiler?style=flat-square)](https://github.com/200762zzy/Blog-Compiler/releases)
[![GitHub stars](https://img.shields.io/github/stars/200762zzy/Blog-Compiler?style=flat-square)](https://github.com/200762zzy/Blog-Compiler/stargazers)
[![GitHub license](https://img.shields.io/github/license/200762zzy/Blog-Compiler?style=flat-square)](https://github.com/200762zzy/Blog-Compiler/blob/main/LICENSE)
[![Windows](https://img.shields.io/badge/Windows-10%20%7C%2011-0078D6?style=flat-square&logo=windows&logoColor=white)](https://github.com/200762zzy/Blog-Compiler/releases)
[![Platforms](https://img.shields.io/badge/Platform-CSDN%20|%20掘金%20|%20博客园-6A5ACD?style=flat-square)](https://github.com/200762zzy/Blog-Compiler/releases)

</div>

---

## 简介

Typora 写笔记，CSDN 发博客，中间差了好几步？

> - 图片全是本地路径，CSDN 看不到
> - 笔记语气太随意，需要润色
> - 手动调格式、传图片、填标签…一篇博客能折腾半小时

**Blog Compiler 帮你一步走完：读 → 改 → 传 → 发。**

---

## 工作流

```
📄 Typora .md 文件
    │
    ▼
┌─────────────────┐
│  解析 Markdown   │  ← 统计段落/代码/表格/图片
├─────────────────┤
│  🤖 AI 改写      │  ← 笔记 → 博主口吻（可选）
├─────────────────┤
│  🖼️ 图片处理     │  ← 图床 / base64 / 掘金原生 CDN
├─────────────────┤
│  📤 多平台发布   │  ← 同时发到 CSDN · 掘金 · 博客园
└─────────────────┘
```

---

## 功能特性

### 📄 Markdown 解析

解析标题、段落、代码块、表格、图片，实时统计展示。

### 🤖 AI 改写

支持的模型（⚙ 设置中配置 API Key）：

| 服务商 | 模型 |
|--------|------|
| OpenAI | `gpt-4o` / `gpt-4o-mini` |
| DeepSeek | `deepseek-chat` / `deepseek-reasoner` |
| 月之暗面 | `moonshot-v1-8k` |
| 阿里通义 | `qwen-max` |
| 智谱 | `glm-4` |
| 自定义 | 任意 OpenAI 兼容模型 |

### 🖼️ 图片处理

| 模式 | 行为 | 适用场景 |
|------|------|----------|
| **上传 scdn.io 图床** | 自动上传到 scdn.io（国内 CDN） | CSDN / 博客园 |
| **掘金原生 CDN 上传** | 通过 ByteDance ImageX 上传到 `byteimg.com` | 掘金发布时自动触发 |
| **生成 alt 文本** | AI 生成描述文字，删除图片路径 | 手动拖图 |
| **保留原路径** | 不处理 | 本地预览 |
| **base64 嵌入** | 发布时可选，100% 可靠 | 兜底方案 |

### 📤 多平台一键发布

| 平台 | 登录方式 | 发布方式 | 图片处理 |
|------|----------|----------|----------|
| **CSDN** | 微信扫码登录（QtWebEngine） | x-ca-signature API | scdn.io 图床 |
| **掘金** | 二维码扫码 + 手动确认 | Cookie API | ByteDance ImageX CDN（自动） |
| **博客园** | 设置中配置 Cookie | XML-RPC | scdn.io 图床 |

- **Cookie 持久化** — 登录后自动保存，下次启动免登录
- **标题自动提取** — 从文章第一个 `# ` 标题自动填充，可手动编辑
- **标签 / 分类** — 发布前设置（各平台独立）
- **并行 / 串行发布** — 可勾选同时发布或逐一顺序发布
- **日志面板** — 实时显示每步操作状态
- **base64 内嵌图片** — 兜底方案，100% 可用（但文章体积变大）

### 📤 导出

- 保存 `.md` 文件（含覆盖确认）
- 复制到剪贴板，直接粘贴到编辑器
- 各平台 Markdown 方言自动适配（CSDN 表格/代码块、掘金图片尺寸等）

### 🚀 v2.1.0 新特性

- **掘金图片上传** — 通过 ByteDance ImageX CDN（`byteimg.com`）自动上传图片，发布时无需额外操作
- **多平台发布** — 支持 CSDN / 掘金 / 博客园三平台一键发布，串行/并行模式可选
- **AI 改写不卡 UI** — 图片上传移至后台线程（`ImageUploadWorker`），改写过程不再冻结界面
- **登录检测优化** — 掘金 SPA 登录支持手动确认按钮，URL 不跳转也能正常登录
- **选中区域改写** — 支持仅改写选中文本，保留上下文不变
- **自定义系统提示词** — 可在设置中编写自定义 AI 提示词，自由控制改写风格
- **草稿历史** — 每次改写自动保存草稿，支持版本回溯

### 🎨 界面

- 暗色模式
- 文件拖拽添加
- 改写前后对比视图
- 改写后内容可编辑
- 图片上传状态实时显示
<img width="2555" height="1523" alt="image" src="https://github.com/user-attachments/assets/4bc50c79-1717-4d18-a1ae-48f341f61f24" />

---

## 快速开始

### 下载即用

[![Download](https://img.shields.io/badge/Download-v2.1.0-2ea44f?style=for-the-badge)](https://github.com/200762zzy/Blog-Compiler/releases/latest/download/BlogCompiler.exe)

1. 下载 `BlogCompiler.exe`
2. 双击运行（无需安装）
3. ⚙ 设置 → 填入 API Key 和模型
4. 拖入 `.md` 文件 → 点击「AI 改写」
5. 选择平台（CSDN / 掘金 / 博客园）→ 扫码登录 → 发布

### 从源码运行

```bash
git clone https://github.com/200762zzy/Blog-Compiler.git
cd Blog-Compiler
pip install -r requirements.txt
python main.py
```

---

## 项目结构

```
Blog-Compiler/
├── main.py               # 入口 + 崩溃处理
├── app.py                # GUI 主窗口
├── parser.py             # Markdown 解析
├── ai_rewriter.py        # AI 改写（支持动态提示）
├── image_handler.py      # 图片正则中心
├── image_uploader.py     # scdn.io 图床上传
├── exporter.py           # 导出 + 多平台格式适配
├── login_window.py       # 扫码登录窗口（CSDN / 掘金通用）
├── settings.py           # 配置管理（加密存储）
├── build.py              # PyInstaller 打包脚本
├── publishers/           # 多平台发布器
│   ├── __init__.py
│   ├── base.py           # 发布器基类
│   ├── csdn.py           # CSDN 发布（x-ca-signature）
│   ├── juejin.py         # 掘金发布（含 ByteDance ImageX 上传）
│   └── cnblogs.py        # 博客园发布（XML-RPC）
├── requirements.txt
└── .github/
    ├── workflows/build.yml
    └── ISSUE_TEMPLATE/
```

---

## 打包 exe

```bash
py build.py
# 输出: dist/BlogCompiler.exe (~233 MB, 含 QtWebEngine)
```

> 注：Windows 上请使用 `py` 而非 `python`，避免触发 Microsoft Store 的 Python 占位符。

---

## License

[MIT](LICENSE)

---

<div align="center">

**如果这个工具对你有帮助，请点 ⭐ Star 支持一下！**

[![GitHub stars](https://img.shields.io/github/stars/200762zzy/Blog-Compiler?style=social)](https://github.com/200762zzy/Blog-Compiler/stargazers)

</div>
