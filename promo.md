<div align="center">

# Blog Compiler

**Markdown 笔记 → AI 改写 → 图片托管 → 一键发布到 CSDN / 掘金 / 博客园**

把「写笔记」和「发博客」之间那堆繁琐操作，全部自动化。

![Release](https://img.shields.io/github/v/release/200762zzy/Blog-Compiler?style=flat-square)
![Stars](https://img.shields.io/github/stars/200762zzy/Blog-Compiler?style=flat-square)
![License](https://img.shields.io/badge/license-MIT-green?style=flat-square)

</div>

---

## 😩 你是不是也这样

- 在 Typora / Obsidian 写了一堆笔记想发博客，结果图片全是本地路径，平台看不到
- 图片传了外链图床，发布时又「**转存失败**」
- 笔记语气太随意，要手动润色成博主口吻
- 格式、标签、分类……一篇博客折腾半小时
- 想同时发到掘金、博客园，还得重复一遍

**Blog Compiler 把这些一次做完：读 → 改 → 传 → 发。**

---

## ✨ 核心能力

### 🤖 AI 改写（流式输出）

- 支持 OpenAI / DeepSeek / Kimi / 通义 / 智谱 / 硅基流动 / 火山方舟 / OpenRouter / Ollama
- **边写边显示**，长文不再干等；代码块、表格原样保留
- 多种语气预设 + 自定义 System Prompt；支持只改写选中段落

### 🖼️ 图片自动处理

- **CSDN 原生图床**：发布前直传 CSDN 自家 CDN，**根治「图片转存失败」**
- 掘金走 ByteDance ImageX CDN 自动上传
- 上传前自动压缩为 **WebP**；支持 **HTTP 代理**

### 📤 多平台一键发布

- **CSDN / 掘金 / 博客园** 一次发布，串行/并行可选
- **系统 WebView2 扫码登录** + **多账号切换**
- 发布结果卡片 + **单平台重试**
- 按平台记忆标签/分类；**AI 生成标题/标签/摘要**
- **更新已发布文章**（CSDN，同标题自动更新，不重复新建）

### 🧰 好用的小细节

- **命令面板（Ctrl+K）**、快捷键、首次运行引导
- 配置**备份/还原**、**发布历史**
- 现代界面：靛青渐变、暗色模式、可折叠工作台
- 安装包仅 **~77 MB**（登录用系统 WebView2，不打包浏览器内核）

---

## 🔄 工作流

```
📄 Markdown 笔记
      │
      ▼
┌──────────────────┐
│  解析 / 统计      │
├──────────────────┤
│  🤖 AI 改写（流式）│
├──────────────────┤
│  🖼️ 图片上传/压缩  │
├──────────────────┤
│  📤 一键发布多平台 │
└──────────────────┘
```

---

## 🚀 快速开始

1. 下载 `BlogCompiler.exe`（Windows 10/11，无需安装）
2. 双击运行 → ⚙ 设置填入 API Key 和模型
3. 拖入 `.md` 文件 → 点「AI 改写」
4. 选平台 → 扫码登录 → 发布

[⬇️ 下载最新版](https://github.com/200762zzy/Blog-Compiler/releases/latest)

---

## 📦 支持平台

| 平台 | 登录 | 发布 |
|------|------|------|
| CSDN | 扫码（WebView2） | ✅ 图片直传 + 更新文章 |
| 掘金 | 扫码（WebView2） | ✅ ImageX 图片上传 |
| 博客园 | API Key | ✅ |
| B站 / 微信 | 规划中 | — |

---

## 🛠️ 技术栈

Python · PySide6 · pywebview（系统 WebView2）· httpx · mistune

---

## 🤝 参与贡献

开源 **MIT**，欢迎 Issue / PR / Star。新手可从 [`good first issue`](https://github.com/200762zzy/Blog-Compiler/labels/good%20first%20issue) 入手。

<div align="center">

**如果它帮你省了时间，点个 ⭐ Star 支持一下！**

https://github.com/200762zzy/Blog-Compiler

</div>

---

## 📣 附：各平台短文案

### 掘金 / CSDN

> **标题**：我做了个开源工具，把 Typora 笔记一键发到 CSDN / 掘金 / 博客园
>
> 写博客最烦发之前的准备：图片本地路径要传图床、笔记语气要润色、格式要调……一篇能折腾半小时。
>
> 于是做了 **Blog Compiler**：拖入 `.md` → AI 改写（流式）→ 图片自动上传/压缩 → 一键发布三大平台。CSDN 图片直传自家 CDN，不再「转存失败」；还支持多账号、AI 生成标题标签、更新已发布文章。
>
> Windows 双击即用，开源免费：https://github.com/200762zzy/Blog-Compiler
>
> 欢迎 Star ⭐ 和提 Issue！

### V2EX（分享创造）

> **[分享创造] Blog Compiler — Markdown 笔记一键发布到 CSDN/掘金/博客园**
>
> 痛点：md 图片是本地路径，发 CSDN 要么转存失败要么手动传图床。
>
> 这个工具把「读 → AI 改写 → 传图 → 发布」串成一步，CSDN 走自家 OSS 图床、掘金走 ImageX，登录用系统 WebView2 扫码。
>
> 开源 MIT，欢迎反馈：https://github.com/200762zzy/Blog-Compiler

### Show HN / dev.to

> **Show HN: Blog Compiler – Turn Markdown notes into published blog posts with AI**
>
> A Windows desktop tool that takes a Typora `.md` file and handles the whole pipeline: AI rewriting (streaming), image re-hosting (CSDN native CDN / ByteDance ImageX), and one-click publishing to CSDN, Juejin and Cnblogs. Login uses the system WebView2, so the app is only ~77 MB.
>
> Open source (MIT): https://github.com/200762zzy/Blog-Compiler — feedback and contributions welcome!
