# Blog Compiler

> 把你的本地 Typora 笔记，一键编译成 CSDN 博客风格的 Markdown。

## 功能

- **📝 MD 解析** — 解析 Markdown 文件，提取文本、代码块、图片、表格
- **🤖 AI 改写** — 调用 LLM API（OpenAI / DeepSeek / 月之暗面等），将笔记改写成博主口吻
- **🖼️ 图片处理** — 自动将本地 Typora 截图上传到 CSDN 服务器
- **📤 一键编译** — AI 改写 → 上传图片 → 导出文件，一条龙
- **📋 导出灵活** — 保存为 `.md` 文件或直接复制到剪贴板

## 截图

*(待补充)*

## 快速开始

### 方式一：下载发布版

从 [Releases](https://github.com/200762zzy/Blog-Compiler/releases) 下载 `BlogCompiler.exe`，直接运行。

### 方式二：源码运行

```bash
# 1. 克隆仓库
git clone https://github.com/200762zzy/Blog-Compiler.git
cd Blog-Compiler

# 2. 安装依赖
pip install -r requirements.txt

# 3. 运行
python main.py
```

## 使用指南

### 1. 配置 AI

点击工具栏「⚙ 设置」，填入你的 API Key 并选择模型。

支持的服务商（自备 API Key）：
| 服务商 | 推荐模型 | 官网 |
|--------|----------|------|
| OpenAI | gpt-4o-mini | https://platform.openai.com |
| DeepSeek | deepseek-chat | https://platform.deepseek.com |
| 月之暗面 | moonshot-v1-8k | https://platform.moonshot.cn |
| 阿里通义 | qwen-max | https://help.aliyun.com/ |
| 智谱 | glm-4 | https://open.bigmodel.cn |

### 2. 登录 CSDN（如需上传图片）

点击「登录 CSDN」→ 用 CSDN App 或微信扫码 → 自动登录。

### 3. 处理文件

- **手动流程**：添加文件 → AI 改写 → 上传图片 → 导出
- **自动流程**：添加文件 → 一键编译（一步到位）

## 项目结构

```
Blog-Compiler/
├── main.py              # 入口（含崩溃日志）
├── app.py               # GUI 主窗口
├── parser.py            # MD 解析器
├── ai_rewriter.py       # AI 改写模块
├── image_handler.py     # 图片处理模块
├── csdn_uploader.py     # CSDN 上传 API
├── login_window.py      # CSDN 扫码登录
├── exporter.py          # 导出模块
├── settings.py          # 配置管理（加密存储）
├── build.py             # 打包脚本
├── requirements.txt
└── project.md           # 完整项目文档
```

## 开发

```bash
# 打包为单文件 exe
python build.py
```

## License

MIT
