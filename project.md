# Blog Compiler — 笔记转 CSDN 博客工具

> 把你的本地 Typora 笔记，一键编译成 CSDN 博客风格的 Markdown。

---

## 项目概述

将 `.md` 笔记文件转化为 CSDN 博客格式，支持：

- **AI 润色**：调用 LLM API 将笔记改写成博主口吻（中度改写）
- **截图处理**：自动将本地 Typora 截图上传至 CSDN 服务器
- **一键导出**：生成 CSDN 兼容的 Markdown 文件

---

## 技术栈

| 层面 | 选型 | 说明 |
|------|------|------|
| 语言 | Python 3.10+ | 生态丰富，文本处理/AI 集成方便 |
| GUI | PySide6 | 原生体验，支持 WebView 嵌入扫码登录 |
| MD 解析 | mistune | Python 最快 MD 解析器，支持 AST |
| HTTP | httpx | 异步支持，调 AI API + 上传图片 |
| AI API | OpenAI 兼容 | 支持 OpenAI / DeepSeek / 月之暗面等 |
| 打包 | PyInstaller | 打包为 Windows 单文件 exe |

---

## 分阶段开发

### Phase 1: 项目骨架 + 基础 GUI + MD 解析 (v0.1)

**目标**：一个能看能点的窗口，能解析 MD 文件。

**文件结构**：
```
Blog-Compiler/
├── main.py              # 程序入口
├── app.py               # GUI 主窗口
├── parser.py            # MD 解析模块 (mistune)
├── settings.py          # 配置管理
├── image_handler.py     # (占位) 图片处理
├── ai_rewriter.py       # (占位) AI 改写
├── csdn_uploader.py     # (占位) CSDN 上传
├── login_window.py      # (占位) 扫码登录
├── exporter.py          # (占位) 导出
├── requirements.txt
├── .gitignore
└── project.md
```

**核心功能**：
- 三栏 GUI 布局：文件列表 / 内容展示 / 日志操作
- 拖拽或按钮添加 `.md` 文件
- 点击文件显示原始 MD 内容
- 解析 MD，在日志区输出统计信息（文本块、图片、代码块数量）

**自测**：
- 启动后窗口显示正常，三栏布局正确
- 添加文件、点击切换、显示内容
- 解析结果与预期一致

**commit**: `v0.1-scaffold`

---

### Phase 2: CSDN 扫码登录 + 图片上传 (v0.2)

**目标**：本地截图能自动上传到 CSDN。

**核心功能**：
- 内嵌浏览器窗口（QWebEngineView）打开 CSDN 登录页
- 用户扫码后自动捕获并持久化 Cookie
- 封装 CSDN 图片上传 API
- 遍历 MD 中的 `![](本地路径)` → 上传 → 替换为 CSDN 链接
- 失败重试 + 进度提示

**自测**：
- 扫码登录成功，Cookie 持久化
- 单张图片上传成功，返回 CSDN URL
- 含图片的 MD 文件全量替换正确
- 网络/权限异常的友好提示

**commit**: `v0.2-image-upload`

---

### Phase 3: AI 改写模块 (v0.3)

**目标**：笔记被 AI 润色成博主风格。

**核心功能**：
- 调用 OpenAI 兼容 API（用户自备 Key）
- 中度改写 Prompt：保留技术准确性 + 增加博主口吻 + 调整结构
- 代码块和图片占位保持不变
- 长文本自动切片
- 改写前/后双栏对比视图

**自测**：
- API Key 配置正常，调用成功
- 代码块、图片链接在改写后保留
- 长文本正确处理
- 失败场景有明确提示

**commit**: `v0.3-ai-rewriter`

---

### Phase 4: 全流程集成 + 导出 (v0.4)

**目标**：一条龙：读 → 改写 → 传图 → 导出。

**核心功能**：
- 一键全流程串联
- 导出为 `.md` 文件或复制到剪贴板
- CSDN Markdown 方言适配
- 各阶段实时进度 + 日志
- 批量处理多个文件
- 暗色模式

**自测**：
- 全流程跑通真实案例
- 批量处理稳定
- 导出格式在 CSDN 编辑器正确渲染

**commit**: `v0.4-integration`

---

### Phase 5: 打包发布 + 文档 (v1.0)

**目标**：普通用户也能用。

**核心功能**：
- PyInstaller 打包为单文件 exe
- 首次启动配置引导
- 崩溃自动保存日志
- README + 使用教程

**自测**：
- 在无 Python 环境的 Windows 上运行正常
- 真实用户场景全流程通过

**commit**: `v1.0-release`

---

## 架构设计

### 模块依赖

```
┌──────────┐     ┌──────────────────────────────────────┐
│  main.py │────▶│              app.py                   │
└──────────┘     │  (PySide6 主窗口, 三栏布局)           │
                 └──┬──────────┬───────────┬────────────┘
                    │          │           │
                    ▼          ▼           ▼
              ┌────────┐ ┌────────┐ ┌──────────┐
              │parser  │ │  AI    │ │  image   │
              │.py     │ │rewriter│ │_handler  │
              │(mistune)│ │.py     │ │.py       │
              └────────┘ └────────┘ └────┬─────┘
                                         │
                                         ▼
                                   ┌──────────┐
                                   │  csdn    │
                                   │_uploader │
                                   │ .py      │
                                   └──────────┘

              login_window.py ───▶ csdn_uploader.py (提供Cookie)
              settings.py ───────▶ 全局配置读写
              exporter.py ───────▶ 最终输出
```

### 数据流

```
.md 文件
   │
   ▼
parser.py 解析 → 结构化数据 (text, code, images, tables)
   │
   ├──▶ [可选] ai_rewriter.py → LLM API → 改写后的文本
   │
   ├──▶ image_handler.py → csdn_uploader.py → 替换图片链接
   │
   └──▶ exporter.py → 输出最终 .md
```

### CSDN 图片上传

```
POST https://blog.csdn.net/phoenix/upload
Cookie: <从扫码登录获取>
Body: multipart/form-data (图片文件)
Response: {"url": "https://img-blog.csdnimg.cn/xxx.png"}
```

### CSDN 扫码登录

```
QWebEngineView → 加载 https://passport.csdn.net/login
用户扫码 → 页面跳转 → cookieStore 捕获 Cookie
Cookie 加密持久化至本地 config.enc
```

### AI 改写 Prompt

```
你是一位CSDN技术博主，请将下面的笔记内容改写成CSDN博客风格：
1. 保持技术准确性，不要编造不存在的功能
2. 语气专业但不枯燥，可以加入"笔者在实际开发中发现..."等个人经验
3. 为长段落添加小标题分隔，提升可读性
4. 代码块、表格保持原样
5. 保留所有图片占位（![]()），不要改动图片路径
6. 输出格式为 Markdown
```

---

## 目录规范

```
Blog-Compiler/
├── main.py                 # 入口
├── app.py                  # GUI 主窗口
├── parser.py               # MD 解析
├── ai_rewriter.py          # AI 改写
├── image_handler.py        # 图片处理
├── csdn_uploader.py        # CSDN 上传
├── login_window.py         # 扫码登录
├── exporter.py             # 导出
├── settings.py             # 配置
├── requirements.txt
├── .gitignore
└── project.md
```

## 分支策略

- `main`: 稳定版本
- `develop`: 开发分支
- `feature/csdn-login`: Phase 2 功能分支
- `feature/ai-rewriter`: Phase 3 功能分支
- `feature/integration`: Phase 4 功能分支
- `release/v1.0`: Phase 5 发布分支

每个 Phase 完成后合并到 `main` 并打 tag。
