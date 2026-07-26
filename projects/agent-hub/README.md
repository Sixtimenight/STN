# Agent Hub

一个使用 Python、LangGraph 和 Tkinter 构建的桌面端多 Agent 任务审批原型。

Agent Hub 让 Codex 先把自然语言任务转成结构化执行计划，再由用户检查、修改、批准或拒绝，最后路由到合适的执行节点。项目重点不是让 Agent 无限制自动执行，而是把人工确认放在真实操作之前。

## 当前功能

- 使用 Codex CLI 生成结构化任务计划
- 在 Claude Code 与 WorkBuddy 两类执行节点之间进行任务路由
- 展示任务摘要、选择理由、执行步骤和验收标准
- 支持用户在执行前编辑、批准或拒绝指令
- 使用 LangGraph `interrupt` 实现人工审批节点
- 在桌面界面中展示规划状态和调用时间线
- 使用 JSON Schema 约束规划器输出

## 当前状态

这是一个可运行的 MVP：

- 规划流程和人工审批流程已经完成
- 执行节点目前使用占位适配器
- 尚未把获批指令真正发送给 Claude Code 或 WorkBuddy

## 工作流程

```text
用户输入任务
    ↓
Codex 只读分析并生成结构化计划
    ↓
Agent Hub 展示计划和建议执行节点
    ↓
用户修改、批准或拒绝
    ↓
已批准任务进入执行适配器
```

## 运行要求

- Windows
- Python 3.11+
- 已安装并登录 Codex CLI

安装依赖：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

启动：

```powershell
python app.py
```

## 文件

- `app.py`：LangGraph 工作流和 Tkinter 界面
- `planner-schema.json`：Codex 规划结果的 JSON Schema
- `requirements.txt`：Python 依赖

## 隐私说明

运行时产生的规划文件、会话日志、缓存和本地环境不会提交到 GitHub。仓库不包含 API Key、登录凭证或个人对话数据。

## 后续计划

- 接入真实的 Claude Code 和 WorkBuddy 执行适配器
- 增加任务取消、超时和失败恢复
- 为审批记录增加可搜索的本地历史
- 增加自动化测试和跨平台启动方式

