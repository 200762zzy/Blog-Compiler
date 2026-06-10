# Blog Compiler 推广文案草稿

## 掘金 / CSDN 发布帖

---

### 标题

> 我做了个工具：把 Typora 笔记一键变成 CSDN 博客，截图自动生成描述，还能 AI 润色

### 正文

你是不是也这样：

在 Typora 里写了一大堆笔记，贴了无数截图，想发到 CSDN 上分享。结果：
- 图片全是 `C:\Users\xxx\typora-user-images\...png`，CSDN 根本看不到
- 笔记语气太随意，还得手动润色一遍
- 格式调来调去，一篇博客能折腾半小时

所以我写了个小工具 **Blog Compiler**。

#### 它能做什么

**1. AI 改写笔记成博客**
支持 DeepSeek、OpenAI、月之暗面等主流模型。把你的笔记丢进去，出来就是博主口吻：
- 代码块、表格保持原样
- 长段落自动加小标题
- 语气专业但不枯燥

**2. 图片自动处理**
笔记里的截图 `![image.png](C:\xxx\...png)` → 自动变成：
`![终端输出截图：ls -la 命令的执行结果]`
保留描述文本，你到 CSDN 拖图上传就行。

**3. 一键导出**
保存为 .md 文件，或者直接复制到剪贴板，粘贴到 CSDN 编辑器即可发布。

#### 适用场景

- Typora / Obsidian 用户想发技术博客
- 学生笔记整理后发布到 CSDN
- 任何 Markdown 笔记转博客的需求

#### 下载

项目完全开源，Windows 直接下载 exe 运行，无需装 Python。

GitHub：https://github.com/200762zzy/Blog-Compiler
下载：https://github.com/200762zzy/Blog-Compiler/releases

欢迎 Star 和 PR 🎉

---

## V2EX 分享帖

> [分享创造] 做了个 Typora 笔记转 CSDN 博客的工具，AI 润色 + 截图自动处理

Typora 写了半年的笔记，最近想整理发 CSDN 博客，结果发现截图全是本地路径，还得一张张上传，太痛苦了。

就写了个桌面小工具：
1. AI 改写笔记 → 博主口吻
2. 截图 → 自动生成描述文字
3. 导出 .md / 复制到剪贴板

支持 DeepSeek / OpenAI / 月之暗面等模型，Windows exe 直接下载。

https://github.com/200762zzy/Blog-Compiler

欢迎提建议 🙏

---

## 知乎问答

> 如何将 Typora 笔记快速转成 CSDN 博客？

回答：

我自己也遇到这个问题，所以写了个工具 Blog Compiler。

工作流：
1. 把你的 .md 笔记拖进工具
2. 点「AI 改写」— 自动润色成博客风格
3. 截图自动生成 alt 描述文本
4. 导出或复制到剪贴板

5. 到 CSDN 编辑器里，粘贴，把图片拖进去替换，发布

中间省掉了我最烦的手动润色和图片处理两步。

开源地址：https://github.com/200762zzy/Blog-Compiler
