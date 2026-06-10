<div align="center">

# Blog Compiler

📝 把你的 Typora 笔记，一键编译成 CSDN 博客风格的 Markdown

[![GitHub release](https://img.shields.io/github/v/release/200762zzy/Blog-Compiler?style=flat-square)](https://github.com/200762zzy/Blog-Compiler/releases)
[![GitHub stars](https://img.shields.io/github/stars/200762zzy/Blog-Compiler?style=flat-square)](https://github.com/200762zzy/Blog-Compiler/stargazers)
[![GitHub license](https://img.shields.io/github/license/200762zzy/Blog-Compiler?style=flat-square)](https://github.com/200762zzy/Blog-Compiler/blob/main/LICENSE)
[![Windows](https://img.shields.io/badge/Windows-10%20%7C%2011-0078D6?style=flat-square&logo=windows&logoColor=white)](https://github.com/200762zzy/Blog-Compiler/releases)
[![Python](https://img.shields.io/badge/Python-3.12-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)

</div>

---

## 简介

**Blog Compiler** 是一个 Windows 桌面工具，解决一个真实的痛点：

> 你在 Typora 里写了满满的笔记，贴了一堆截图，想发到 CSDN 博客上。结果发现：
> - 图片全是本地路径，CSDN 看不到
> - 笔记语气太随意，需要润色成博客风格
> - 手动调整格式费时费力

**Blog Compiler 一键搞定**。

---

## 功能预览

```
┌─────────────────────────────────────────────────────┐
│  Blog Compiler                                      │
├─────────────────────────────────────────────────────┤
│  [+ 添加文件]  [清空列表]  [暗色模式]  [⚙ 设置]    │
├──────────┬──────────────────────┬───────────────────┤
│ 文件列表  │    原文 / 改写后     │   操作面板        │
│          │                      │                   │
│ □ linux  │  # Linux 基础指令    │  [AI 改写]        │
│ □ 笔记1   │  ...                │  [导出文件]       │
│ □ 任务二  │                     │  [复制到剪贴板]   │
│          │                     │                   │
│          │                     │  运行日志          │
│          │                     │  ┌─────────────┐  │
│          │                     │  │ [00:00] 就绪  │  │
├──────────┴──────────────────────┴───────────────────┤
│  就绪  |  文件: 3  |  图片: 5                       │
└─────────────────────────────────────────────────────┘
```

> 🖼️ *截图待补充 — 欢迎 PR 贡献截图*

---

## 功能特性

### 📄 Markdown 解析
- 解析标题、段落、代码块、表格、图片
- 统计信息实时展示

### 🤖 AI 改写
- 调用 LLM API 将笔记改写成博客风格
- **中度改写**：保留技术准确性 + 增加博主口吻 + 优化结构
- 代码块和表格保持原样
- 支持多种模型：

| 服务商 | 模型 | 配置方式 |
|--------|------|----------|
| OpenAI | `gpt-4o` / `gpt-4o-mini` | ⚙ 设置 → API Key |
| DeepSeek | `deepseek-chat` / `deepseek-reasoner` | ⚙ 设置 → API Key |
| 月之暗面 | `moonshot-v1-8k` | ⚙ 设置 → API Key |
| 阿里通义 | `qwen-max` | ⚙ 设置 → API Key |
| 智谱 | `glm-4` | ⚙ 设置 → API Key |
| 自定义 | 任意 OpenAI 兼容模型 | ⚙ 设置 → 手动输入 |

### 🖼️ 图片处理
- 自动为截图生成描述性的 `alt` 文本
- 示例：`![image.png](C:\path\...png)` → `![终端输出截图：ls -la 命令的执行结果]`
- 你拿到 CSDN 编辑器后拖图上传即可

### 📤 导出
- 保存为 `.md` 文件
- 直接复制到剪贴板，粘贴到 CSDN 编辑器
- CSDN Markdown 方言自动适配（表格格式、代码块标识）

### 🎨 界面
- 暗色模式
- 文件拖拽添加
- 改写前后对比视图

---

## 快速开始

### 下载即用

[![Download](https://img.shields.io/badge/Download-v1.0.0-2ea44f?style=for-the-badge)](https://github.com/200762zzy/Blog-Compiler/releases/download/v1.0.0/BlogCompiler.exe)

1. 下载 `BlogCompiler.exe`
2. 双击运行（无需安装）
3. 点击 ⚙ 设置，填入你的 API Key 和模型
4. 拖入 `.md` 文件或点击「+ 添加文件」
5. 点击「AI 改写」→「导出文件」

### 配置 AI

| 字段 | 说明 |
|------|------|
| API Key | 你的 API 密钥（OpenAI / DeepSeek 等） |
| 模型 | 选择或手动输入模型名 |
| API 地址 | 对应服务商的 API Base URL |

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
├── main.py              # 入口
├── app.py               # GUI 主窗口
├── parser.py            # MD 解析器
├── ai_rewriter.py       # AI 改写模块
├── image_handler.py     # 图片处理
├── exporter.py          # 导出模块
├── settings.py          # 配置管理（加密存储）
├── build.py             # 打包脚本
├── requirements.txt
└── .github/
    └── workflows/
        └── build.yml    # CI 自动打包
```

---

## 开发指南

### 打包为 exe

```bash
python build.py
# 输出: dist/BlogCompiler.exe
```

### 贡献

PR、Issue、Star 都是欢迎的。

---

## License

[MIT](LICENSE)

---

<div align="center">

**如果这个工具对你有帮助，请点 ⭐ Star 支持一下！**

[![GitHub stars](https://img.shields.io/github/stars/200762zzy/Blog-Compiler?style=social)](https://github.com/200762zzy/Blog-Compiler/stargazers)

</div>
