# Blog Compiler — 架构说明

> Markdown 笔记 → AI 改写 → 图片托管 → 一键发布到 CSDN / 掘金 / 博客园

当前版本 **v3.2.0**（见 [version.py](version.py)）。

本文档描述**当前**架构。历史的分阶段开发计划（v0.1 时期的五阶段规划）已不适用，
当时的 `csdn_uploader.py` 上传方案、`config.enc` 加密 Cookie 等设计都已被替换。

---

## 技术栈

| 层面 | 选型 | 说明 |
|------|------|------|
| 语言 | Python 3.12+ | 主目标平台 Windows 10 / 11 |
| GUI | PySide6 | 原生窗口，靛青渐变设计系统 |
| 扫码登录 | pywebview + 系统 WebView2 | 独立子进程运行，安装包不含浏览器内核 |
| MD 解析 | mistune | 解析统计 + HTML 预览 |
| HTTP | httpx | 统一经 `http_client` 工厂，支持代理 |
| 配置加密 | cryptography (Fernet) | 加密 API Key 等敏感项 |
| 打包 | PyInstaller | 单文件 exe，本地构建约 77 MB、CI 约 54 MB |

---

## 目录结构

```
Blog-Compiler/
├── main.py                 # 入口 + 崩溃日志 + --login-webview 子进程分支
├── app.py                  # GUI 主窗口、对话框、后台 Worker、发布编排
├── theme.py                # 设计系统：DARK/LIGHT token + QSS 模板
├── icons.py                # 内联 SVG 图标（currentColor 替换 + 缓存）
├── parser.py               # Markdown 解析与统计
├── image_handler.py        # 图片正则 IMAGE_PATTERN（单一来源）
├── image_processor.py      # 上传前缩放 / 转 WebP（基于 Qt，无额外依赖）
├── image_uploader.py       # scdn.io 图床上传（多 CDN 轮询降级）
├── ai_rewriter.py          # OpenAI 兼容 API：流式改写 / 分块 / 生成标题标签
├── exporter.py             # 导出文件 / 剪贴板 / 平台方言适配
├── settings.py             # 配置读写（~/.blog-compiler）+ 备份还原
├── http_client.py          # 共享 httpx 工厂（全局代理注入）
├── login_window.py         # 登录对话框（子进程调度 + 手动 Cookie 降级）
├── webview_login.py        # WebView2 登录助手（独立进程）
├── image_base64.py         # 图片转 data URI（发布时可选内嵌）
├── requirements-dev.txt    # 测试依赖
├── build.py                # PyInstaller 构建脚本（改打包配置改这里，不要改 .spec）
├── publishers/
│   ├── base.py             # BasePublisher / PublishResult
│   ├── __init__.py         # 发布器注册表
│   ├── csdn.py             # CSDN 保存文章
│   ├── csdn_sign.py        # CSDN x-ca HMAC 签名（单一来源）
│   ├── csdn_image.py       # CSDN 原生图床（华为 OBS 直传）
│   ├── juejin.py           # 掘金（草稿 → 发布，ImageX 图片上传）
│   └── cnblogs.py          # 博客园（XML-RPC / MetaWeblog）
├── tools/                  # 接口探测脚本（人工运行，不参与打包）
├── tests/                  # pytest 用例
└── .github/workflows/      # CI：打 tag 构建并上传 Release
```

---

## 模块依赖

```
main.py ──▶ app.py（PySide6 主窗口）
              │
              ├─▶ parser.py ──▶ image_handler.py
              ├─▶ ai_rewriter.py ──▶ http_client.py
              ├─▶ image_uploader.py ──▶ image_processor.py
              │                    └─▶ http_client.py
              ├─▶ exporter.py
              ├─▶ settings.py ──▶ publishers/csdn_sign.py（CA 默认值）
              ├─▶ login_window.py ──▶ webview_login.py（子进程）
              └─▶ publishers/（注册表）
                    ├─ csdn.py ──▶ csdn_sign.py
                    │          └─▶ csdn_image.py ──▶ csdn_sign.py
                    ├─ juejin.py
                    └─ cnblogs.py
```

---

## 数据流

### 改写链路

```
选中 .md 文件（拖拽 / 对话框 / Ctrl+O）
   │
   ▼
parser.parse_markdown() → 段落/代码块/表格/标题统计 + 图片列表
   │
   ├─ 图片模式 = upload ──▶ ImageUploadWorker（后台线程）
   │                            scdn.io 上传 → 替换正文中的本地路径
   │
   ▼
_build_system_prompt(模式, 语气)
   │
   ▼
RewriteWorker ──▶ AIRewriter.rewrite_stream()
   │                 ├─ _split_into_blocks()：围栏代码块原子化，不会被切断
   │                 └─ 逐块调用 /chat/completions（stream=True）
   │
   ▼
chunk 信号（80ms 节流）→ 改写后页签实时刷新
   │
   ▼
完成 → 存草稿（内存）→ 启用导出 / 发布
```

### 发布链路

```
PublishDialog
   │
   ├─ 标题：默认取正文第一个 "# " 标题
   ├─ base64 内嵌（可选）：图片转 data URI
   ▼
_publish_platforms()（串行默认 / 可选 ThreadPoolExecutor 并行）
   │
   ▼
_publish_one(平台)
   │
   ├─ Exporter.adapt_for(平台)          # 平台方言：代码块语言、表格、图片尺寸
   ├─ csdn  → process_markdown_images() # 直传 CSDN 自家 CDN
   ├─ juejin → ImageX 上传
   ▼
PublishResult → 结果卡片（可单平台重试）+ 发布历史（最多 50 条）
```

---

## 关键设计

### 界面结构（v3.2.0 起）

窗口自上而下是：命令栏 → **四步导航** → 主体三栏 → 常驻操作栏 → 状态栏。

```
命令栏        品牌 / 当前文件 / 搜索 / 命令面板 / 主题 / 设置
四步导航      读取笔记 › AI 改写 › 图片处理 › 发布   （读过并完成的步骤显示 ✓）
主体  ├ 文档列表（可收起）
      ├ 原文 | 改写后（并排，可再展开「预览」成三栏）
      └ 任务面板（只显示当前这一步的设置）
操作栏        AI 改写 / 复制 / 导出 / 多平台发布 + 运行日志
```

要点：

- **点步骤就换左侧表单**（`Stepper.step_clicked` → `_go_to_step` → `task_stack`），
  十几组控件不再挤在一列里
- 四个步骤面板各自在 `_build_step_*` 里构建，新增设置先想清楚属于哪一步
- **原文与改写后并排**是为了逐段对照；两者用的是同一个 `ImageHandler.IMAGE_PATTERN`
  体系，改一处不要漏另一处
- 底部操作栏**不随步骤切换**，保证复制/导出/发布随时可用
- 发布前检查（`_update_precheck`）在本地就能判定的问题上给出提示，
  例如标题过长、图片路径不存在、代码块围栏数为奇数

### 登录走独立子进程

`login_window.spawn_webview_login()` 通过 `subprocess` 启动
`main.py --login-webview <json>`：子进程用 pywebview 打开系统 WebView2 登录页，
轮询认证 Cookie（如 CSDN 的 `UserName`、掘金的 `sessionid`），
成功后把结果写入临时文件（冻结的 windowed exe 没有可用 stdout），
同时打印 `__BLOGC_COOKIES__` 标记行。主进程优先读文件，失败再解析 stdout，
最后降级为手动粘贴 Cookie。

放在子进程里是为了避免 pywebview 与 PySide6 的事件循环冲突。

### 图片处理三层

| 层 | 模块 | 作用 |
|----|------|------|
| 上传前优化 | `image_processor` | 超过 `image_max_width` 等比缩小，重新编码为 WebP（体积更小才替换） |
| 通用图床 | `image_uploader` | scdn.io，5 个 CDN 域名依次轮询，网络错误指数退避重试 |
| 平台原生 | `publishers/csdn_image`、`publishers/juejin` | CSDN 直传自家 CDN（华为 OBS），掘金走 ByteDance ImageX |

CSDN 图片单张失败**不阻断发布**：保留原链接并记入 `PublishResult.warnings`，
在发布日志中提示「图片未转存」。

### CSDN 签名单一来源

`publishers/csdn_sign.py` 是 x-ca HMAC 签名的唯一实现，被
`csdn.py`、`csdn_image.py` 和 `tools/probe_publish_api.py` 共用。

签名模板是固定的 7 行结构，其中 **Accept 固定按 `*/*`、Content-Type 固定按
`application/json` 参与签名**（与请求实际发送的头无关）。改动模板会导致网关
返回 401/403，`tests/test_csdn_sign.py` 锁定了这个格式。

### AI 默认值与 max_tokens 回退

**默认厂商只能有一个来源。** `ai_rewriter.SUPPORTED_MODELS` 的第一项即默认厂商，
`DEFAULT_MODEL` / `DEFAULT_API_BASE` / `default_config()` 都从它取。
不要在别处再写一份模型名——之前 `app.py` 有两处默认值是 OpenAI 的
`gpt-4o-mini`，另有一处落回 DeepSeek，导致界面显示一家、请求发去另一家。

模型下拉框是**可编辑**的：选中预设项时 `currentText()` 拿到的是 label
（如 `OpenAI GPT-5.5`），直接当模型名发给 API 会失败。保存设置时统一经
`resolve_model_name()` 还原成 value；只有真正手输的名字才原样使用。

新一代 OpenAI 模型（GPT-5 系列）不再接受 `max_tokens`，会直接返回 400。
`ai_rewriter` 检测到错误信息里出现 `max_completion_tokens` 时，会**自动改用新
参数名重试一次**（`needs_max_completion_tokens()` / `retry_with_max_completion_tokens()`）。
只在明确提到新参数名时回退，所以 Key 无效之类的真错误不会被吞掉重试。

### 网络请求统一走 http_client

`http_client.client()` 在创建 httpx 客户端时注入用户配置的代理，
`get/post/put` 辅助函数会自动关闭客户端。**新增网络调用必须走它**，不要直接 `httpx.Client()`，否则代理设置对该调用不生效。

### 发布器插件

`publishers/base.py` 定义接口（`name` / `is_logged_in` / `login` / `publish`），
`publishers/__init__.py` 的 `init_publishers(settings)` 构造实例存入注册表。

新增一个平台：

1. 照 `publishers/juejin.py` 写一个 `BasePublisher` 子类
2. 在 `publishers/__init__.py` 注册
3. 如需平台方言，在 `exporter.py` 的 `PLATFORM_ADAPTERS` 加适配器

主界面发布卡片会遍历 `get_publishers()` 自动列出，无需改 UI 代码。

### base64 内嵌

发布对话框勾选「将图片转为 base64 嵌入」时，`image_base64.embed_images()` 把正文里
每个图片引用换成 `data:<mime>;base64,...`。本地文件直读，http(s) 链接经
`http_client` 下载（因此受代理设置影响）；单张失败保留原样，不影响其余图片。
`MainWindow._embed_images_base64` 只是这个模块的薄封装，实现不要写回 UI 层。

---

## 配置

位置 `~/.blog-compiler/`：

- `config.json` — 明文 JSON
- `.key` — Fernet 密钥，用于加解密敏感项。读取后会缓存在内存里
  （`_get_cipher()`），所以**替换 `KEY_FILE` 或写入新密钥后必须调用
  `_reset_cipher_cache()`**，否则会拿旧密钥去解密（`import_config` 已经这样处理）

### 批量写入

`set()` 每调用一次就重写整个配置文件。连续改多项时要包在 `batch()` 里，
结束时只落盘一次：

```python
with settings.batch():
    settings.set("ai_model", model)
    settings.set("http_proxy", proxy)   # 到这里才写盘，且只写一次
```

保存设置界面从 12 次写盘降到 1 次，账号切换从 4 次降到 1 次。
块内抛异常也会落盘——那些改动已经生效，不写反而会丢数据。

敏感项以密文存于 `config.json`，经 `set_encrypted` / `get_encrypted` 读写：

- `ai_api_key` — AI 服务的 Key
- `cnblogs_api_key` — 博客园 MetaWeblog Key，用 `set_cnblogs_api_key` /
  `get_cnblogs_api_key` 访问（不要直接用 `get`，否则拿到的是密文）。
  明文与密文共用同一个键名，所以账号管理里「原样复制该键」的逻辑自动走加解密。
  早期版本存下的明文会在启动时由 `migrate_cnblogs_api_key()` 就地加密，老用户无感。

「导出配置」会把数据与密钥一起打包，便于迁移；「导入配置」会覆盖当前配置。

主要配置项：

| 分类 | 键 |
|------|-----|
| AI | `ai_api_key`(密文)、`ai_api_base`、`ai_model`、`ai_temperature`、`ai_max_tokens`、`ai_tone`、`ai_tone_custom`、`ai_custom_prompt`、`ai_use_custom_prompt` |
| 网络 | `http_proxy` |
| 图片 | `image_compress`、`image_max_width` |
| 账号 | `csdn_cookies`、`juejin_cookies`、`cnblogs_username`、`cnblogs_api_key`(密文)、`cnblogs_blog_id`、`accounts`（多账号） |
| 发布 | `publish_presets`、`publish_history` |
| CSDN 网关 | `ca_key`、`ca_secret`（默认值见 `publishers/csdn_sign.py`） |
| 其他 | `onboarding_done`、`dark_mode` |

---

## 开发约定

- **耗时操作必须放后台线程**（参考 `RewriteWorker` / `ImageUploadWorker` / `MetaWorker`），否则冻结界面
- **网络调用统一走 `http_client`**，保证代理生效
- **图片路径正则统一用 `image_handler.IMAGE_PATTERN`**，不要在别处另写一份
- 日志与提示信息统一用中文
- 不加冗余注释，让代码自解释；只在复杂逻辑处写必要说明
- 主题改动改 `theme.py` 的 token 字典，QSS 模板只写一次，全局换肤
- 改打包配置改 `build.py`，不要手改 PyInstaller 生成的 `.spec`
- **图片路径的「提取」和「替换」必须用同一个正则**（`ImageHandler.replace_images`）。
  用裸字符串替换会漏掉带 title 的图片（`![](path "标题")`），
  结果是图传上去了、正文里留的还是本地路径
- **平台对字段的硬性要求要在本地就校验**。掘金要求 `brief_content`
  至少 50 个字符（见 `publishers/juejin.py` 的 `build_brief_content`），
  这类限制只会在调接口时以错误响应暴露，所以都放进自动化测试
- **替换 `settings.KEY_FILE` 之后要 `_reset_cipher_cache()`**，
  密钥是带缓存的（见「配置」一节的说明）

---

## 测试

```bash
pip install -r requirements-dev.txt
py -m pytest -q
```

覆盖：Markdown 解析统计、配置读写与加解密、备份还原、图床上传的
CDN 轮询/重试/临时文件清理、CSDN 签名格式、CSDN 图片处理、
`http_client` 代理注入与参数透传、base64 内嵌、发布器结构与导出适配。

约定：

- 网络调用一律用鸭子类型 Fake 客户端注入，不联网
- 需要磁盘的用例用 `work_dir` 夹具（见 `tests/conftest.py`），
  默认落在仓库旁的 `.pytest_tmp/`，可用 `BLOGC_TEST_TMP` 覆盖。
  该夹具用 `mkdir()` 而非 `tempfile.mkdtemp()`：后者创建的目录是 0700，
  受限沙箱令牌会写不进去
- `app.py` 是 GUI 编排层，没有自动化测试；它的非 UI 逻辑（如 base64 内嵌）
  应抽到独立模块再测，UI 里只留薄封装

---

## 打包与发布

```bash
py build.py
# 输出: dist/BlogCompiler.exe (~77 MB)
```

> Windows 上请用 `py` 而不是 `python`，避免触发 Microsoft Store 的占位符。

体积控制的关键在 `build.py` 的 `EXCLUDES`：排除 QtWebEngine、QtTest、QtSql 等
未使用模块，登录改用系统 WebView2，因此不打包浏览器内核。

**体积会因构建机而异**：CI 产出的正式版约 **54 MB**，本地开发机可能到 **77 MB**。
差异来自本机 Python 环境里多装的可选依赖被打进包（主要是 `pythonnet`），
不是 CI 产物有问题——判断产物是否完整要看归档里的模块，不能只看体积。

发版流程：改 `version.py` → 更新 README → **在网页手动创建 Release**（这一步不能省，
否则 CI 会用自己的机器人身份替你建一个空 Release）→ 打 `v*` tag 触发 CI 挂上 exe。
详见 [CONTRIBUTING.md](CONTRIBUTING.md) 的「发布新版本」。

---

## 分支策略

- `main` — 稳定版本
- `feat/xxx`、`fix/xxx`、`docs/xxx` — 特性分支，PR 合入 `main`

详见 [CONTRIBUTING.md](CONTRIBUTING.md)。
