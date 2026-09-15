# 参与贡献

感谢你有兴趣为 **Blog Compiler** 做出贡献！🎉

无论是修复 Bug、新增功能、完善文档，还是提出建议，我们都非常欢迎。本文档会帮你快速上手。

---

## 目录

- [行为准则](#行为准则)
- [环境准备](#环境准备)
- [克隆与本地运行](#克隆与本地运行)
- [项目架构](#项目架构)
- [代码风格约定](#代码风格约定)
- [提交 Pull Request](#提交-pull-request)
- [提交 Issue](#提交-issue)
- [新手任务](#新手任务)

---

## 行为准则

- 尊重每一位贡献者，保持友善、专业的沟通
- 就事论事，讨论代码而非人
- 对新手友好，欢迎提问

---

## 环境准备

| 项目 | 要求 |
|------|------|
| 操作系统 | Windows 10 / 11（主目标平台） |
| Python | 3.12+ |
| 包管理 | pip |

> **Windows 用户注意**：请使用 `py` 而不是 `python` 命令，避免触发 Microsoft Store 的 Python 占位符。

---

## 克隆与本地运行

```bash
git clone https://github.com/200762zzy/Blog-Compiler.git
cd Blog-Compiler
pip install -r requirements.txt
py main.py
```

打包为 exe（可选）：

```bash
py build.py
# 输出: dist/BlogCompiler.exe (~236 MB, 含 QtWebEngine)
```

---

## 项目架构

```
Blog-Compiler/
├── main.py               # 入口 + 崩溃处理
├── app.py                # GUI 主窗口
├── parser.py             # Markdown 解析
├── ai_rewriter.py        # AI 改写（支持动态提示）
├── image_handler.py      # 图片正则中心
├── image_uploader.py     # scdn.io 图床上传（多 CDN 轮询）
├── exporter.py           # 导出 + 多平台格式适配
├── login_window.py       # 扫码登录窗口（CSDN / 掘金通用）
├── settings.py           # 配置管理（加密存储）
├── build.py              # PyInstaller 打包脚本
├── publishers/           # 多平台发布器
│   ├── base.py           # 发布器基类
│   ├── csdn.py           # CSDN 发布（x-ca-signature）
│   ├── csdn_image.py     # CSDN 原生图床（华为 OBS）
│   ├── juejin.py         # 掘金发布（含 ByteDance ImageX 上传）
│   └── cnblogs.py        # 博客园发布（XML-RPC）
├── requirements.txt
└── .github/
    ├── workflows/build.yml
    └── ISSUE_TEMPLATE/
```

修改某个平台的行为时，通常只需改动 `publishers/` 下对应的文件；涉及 UI 的改动集中在 `app.py`。

---

## 代码风格约定

- **不要添加多余注释**，让代码自解释；仅在逻辑复杂处写必要说明
- 遵循现有代码的命名与结构风格，优先复用已有工具函数
- GUI 相关代码使用 PySide6 惯例；耗时操作务必放到后台线程（参考 `ImageUploadWorker`），避免阻塞 UI
- 日志、提示信息统一使用中文
- 提交前请确认程序能正常启动：`py main.py`

---

## 提交 Pull Request

1. **Fork** 本仓库到你的账号
2. 从 `main` 切出特性分支，命名建议：
   - `feat/xxx` — 新功能
   - `fix/xxx` — Bug 修复
   - `docs/xxx` — 文档
3. 提交时使用清晰的 commit message，推荐前缀：
   - `feat: 新增 xxx`
   - `fix: 修复 xxx`
   - `chore: 杂项（版本号、依赖等）`
   - `docs: 文档更新`
4. 推送到你的 fork，然后向上游 `main` 发起 PR
5. 在 PR 描述中说明：
   - 改了什么、为什么改
   - 如何验证（复现步骤 / 截图）
   - 关联的 Issue 编号（如 `Closes #12`）

PR 合并前请确保：

- [ ] 程序可正常启动，无报错
- [ ] 改动范围聚焦，未夹带无关修改
- [ ] 已更新相关文档（如需要）

---

## 提交 Issue

提交前请先搜索是否已有相同 Issue。我们提供了两种模板：

- **Bug 报告** — 描述问题、复现步骤、预期行为、日志、环境
- **功能建议** — 说明动机、期望方案、备选方案

> 报告 Bug 时，请尽量附上「保存日志」按钮导出的日志内容，能大幅加快定位速度。

---

## 新手任务

如果你是第一次参与开源，可以从标记了 [`good first issue`](https://github.com/200762zzy/Blog-Compiler/labels/good%20first%20issue) 的 Issue 入手——这些任务范围清晰、难度适中。

有疑问可以直接在 Issue 下留言，我们会尽快回复。

---

<div align="center">

**再次感谢你的贡献！** ❤️

</div>
