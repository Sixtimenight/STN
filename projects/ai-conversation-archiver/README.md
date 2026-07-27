# AI Conversation Archiver

一个面向个人知识管理的 AI 对话归档工作流：把平台中的历史会话保存为结构化 JSON、可阅读 Markdown、平台索引和本地附件，再放入 Obsidian 长期管理。

## 已完成的实践

- 整理 DeepSeek 100 个会话、豆包 40 个会话
- 共处理 1,613 条消息
- 为会话保留稳定 ID，避免同名标题互相覆盖
- 将消息转换为带 Frontmatter 的 Markdown
- 为平台生成独立索引
- 下载图片和视频附件并生成状态清单
- 检查 JSON、Markdown、Frontmatter 和附件对应关系

## 数据结构

公开示例使用以下最小结构：

```json
{
  "conversation_id": "demo-001",
  "platform": "example",
  "title": "示例对话",
  "messages": [
    {"role": "user", "content": "你好"},
    {"role": "assistant", "content": "你好，有什么可以帮你？"}
  ],
  "assets": []
}
```

## 附件下载

`download-assets.ps1` 读取归档 JSON 中的 `assets`，按 URL 哈希生成稳定文件名，并把成功、失败、文件类型和文件大小写入 `download-manifest.json`。

```powershell
.\download-assets.ps1 `
  -RawDir .\exports `
  -AttachmentDir .\attachments
```

## 目录建议

```text
archive/
├── 00-raw/
├── 10-conversations/
├── 20-attachments/
├── 90-index/
└── export-log.md
```

## 隐私边界

此公开版本不包含任何真实聊天正文、原始导出包、个人图片、账号 Cookie、临时访问参数或本地下载清单，只保留通用脚本、结构说明和虚构示例。

## 当前限制

各平台页面结构不同，完整会话提取仍依赖已登录浏览器和平台适配逻辑；当前公开脚本主要覆盖附件落盘与清单生成。

