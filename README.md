# STN Projects

这里收录我的 AI、自动化与 Web3 实践项目。每个项目都放在 `projects/` 下，并独立提供说明、源代码和运行方式。

## 项目

| 项目 | 简介 | 技术 |
| --- | --- | --- |
| [Agent Hub](projects/agent-hub/README.md) | 带人工审批流程的桌面端多 Agent 任务控制台原型 | Python、LangGraph、Tkinter、Codex CLI |
| [AI Conversation Archiver](projects/ai-conversation-archiver/README.md) | 将多平台 AI 对话整理为 JSON、Markdown、索引和本地附件 | PowerShell、JSON、Markdown、Obsidian |
| [AI/Web3 Opportunity Radar](projects/ai-web3-opportunity-radar/README.md) | 对 AI 与 Web3 机会进行检索、核验、评分和风险过滤 | Research Workflow、Markdown、AI |
| [Study Review Runner](projects/study-review-runner/README.md) | 从 Word 题库顺序抽题并持久化复习进度 | Python、DOCX、JSON |
| [AI Content Workflow](projects/ai-content-workflow/README.md) | 从资料研究到文章、配图和社交媒体内容的生产流程 | AI Research、Markdown、Visual Prompts |

## 仓库结构

```text
STN/
├── README.md
└── projects/
    ├── agent-hub/
    ├── ai-conversation-archiver/
    ├── ai-web3-opportunity-radar/
    ├── study-review-runner/
    └── ai-content-workflow/
```

每个项目采用相同的基本结构：

```text
project-name/
├── README.md
├── source code or workflow templates
└── sanitized examples
```

实际运行数据、账号凭证、私人对话、缓存和本机环境不会提交到仓库。
