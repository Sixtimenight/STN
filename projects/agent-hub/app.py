from __future__ import annotations

import json
import operator
import os
import queue
import shutil
import subprocess
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Annotated, Literal, TypedDict

import tkinter as tk
from tkinter import messagebox, ttk

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt


APP_DIR = Path(__file__).resolve().parent
LOG_DIR = APP_DIR / "sessions"
LOG_DIR.mkdir(exist_ok=True)
RUNTIME_DIR = APP_DIR / "runtime"
RUNTIME_DIR.mkdir(exist_ok=True)
PLANNER_SCHEMA = APP_DIR / "planner-schema.json"
PLANNER_EVENTS: queue.Queue[dict] = queue.Queue()


class HubState(TypedDict, total=False):
    task: str
    target: str
    proposed_prompt: str
    approved_prompt: str
    status: str
    execution_result: str
    plan_summary: str
    target_reason: str
    plan_steps: list[str]
    success_criteria: list[str]
    planner_thread_id: str
    timeline: Annotated[list[str], operator.add]


def now() -> str:
    return datetime.now().strftime("%H:%M:%S")


def emit_planner_event(kind: str, text: str) -> None:
    PLANNER_EVENTS.put({"kind": kind, "text": text, "time": now()})


def find_codex_executable() -> str:
    appdata = Path(os.environ.get("APPDATA", ""))
    native = (
        appdata
        / "npm"
        / "node_modules"
        / "@openai"
        / "codex"
        / "node_modules"
        / "@openai"
        / "codex-win32-x64"
        / "vendor"
        / "x86_64-pc-windows-msvc"
        / "codex"
        / "codex.exe"
    )
    if native.exists():
        return str(native)
    executable = shutil.which("codex.exe")
    if executable:
        return executable
    raise RuntimeError("没有找到 Codex CLI 可执行文件")


def run_codex_planner(task: str, requested_target: str) -> tuple[dict, str]:
    codex_executable = find_codex_executable()
    login_check = subprocess.run(
        [codex_executable, "login", "status"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=15,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    if login_check.returncode != 0:
        raise RuntimeError(
            "Agent Hub 使用的 Codex CLI 尚未登录。"
            "它和当前 Codex 桌面客户端是两个独立入口，需要先完成一次 CLI 登录。"
        )

    target_rule = {
        "auto": "请根据任务性质，在 Claude Code 和 WorkBuddy 之间选择更合适的执行节点。",
        "claude": "用户已指定 Claude Code；target 必须是 claude。",
        "workbuddy": "用户已指定 WorkBuddy；target 必须是 workbuddy。",
    }[requested_target]
    planner_prompt = f"""
你是 Agent Hub 中的 Codex 规划器。你的工作是规划和委派，不能修改任何文件，也不能执行任务本身。

用户任务：
{task}

可用执行节点：
- Claude Code：适合代码、仓库分析、调试、实现、测试和技术评审。
- WorkBuddy：适合资料整理、办公内容、写作、知识库和非代码型任务。

节点选择规则：
{target_rule}

请输出一份可供用户审批的计划。execution_prompt 必须是可以直接发送给选定执行节点的完整指令；
必须说明边界、交付物和验收标准。只输出符合指定 JSON Schema 的内容。
""".strip()

    run_id = uuid.uuid4().hex
    output_path = RUNTIME_DIR / f"planner-{run_id}.json"
    command = [
        codex_executable,
        "exec",
        "--json",
        "--sandbox",
        "read-only",
        "--skip-git-repo-check",
        "--output-schema",
        str(PLANNER_SCHEMA),
        "--output-last-message",
        str(output_path),
        "-C",
        str(APP_DIR.parent),
        planner_prompt,
    ]

    emit_planner_event("status", "Codex 已开始分析任务")
    process = subprocess.Popen(
        command,
        cwd=APP_DIR.parent,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=subprocess.CREATE_NO_WINDOW,
    )

    planner_thread_id = ""
    assert process.stdout is not None
    for raw_line in process.stdout:
        line = raw_line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        event_type = event.get("type", "")
        if event_type == "thread.started":
            planner_thread_id = event.get("thread_id", "")
            emit_planner_event("status", "Codex 规划会话已建立")
        elif event_type == "turn.started":
            emit_planner_event("status", "Codex 正在制定计划")
        elif event_type == "item.completed":
            item = event.get("item", {})
            item_type = item.get("type")
            if item_type == "command_execution":
                emit_planner_event("activity", "Codex 只读查看了项目信息")
            elif item_type == "plan":
                emit_planner_event("activity", "Codex 已更新任务拆分")
        elif event_type == "turn.completed":
            emit_planner_event("status", "Codex 已完成规划")
        elif event_type in {"turn.failed", "error"}:
            emit_planner_event("error", "Codex 规划过程中发生错误")

    return_code = process.wait()
    if return_code != 0:
        raise RuntimeError(f"Codex 规划失败，退出代码：{return_code}")
    if not output_path.exists():
        raise RuntimeError("Codex 没有生成结构化计划文件")

    try:
        plan = json.loads(output_path.read_text(encoding="utf-8"))
    finally:
        output_path.unlink(missing_ok=True)
    return plan, planner_thread_id


def prepare_prompt(state: HubState) -> HubState:
    plan, planner_thread_id = run_codex_planner(state["task"], state["target"])
    target_name = "Claude Code" if plan["target"] == "claude" else "WorkBuddy"
    return {
        "target": plan["target"],
        "proposed_prompt": plan["execution_prompt"],
        "plan_summary": plan["summary"],
        "target_reason": plan["target_reason"],
        "plan_steps": plan["steps"],
        "success_criteria": plan["success_criteria"],
        "planner_thread_id": planner_thread_id,
        "status": "waiting_for_approval",
        "timeline": [
            f"{now()}  Codex 已完成真实规划",
            f"{now()}  Codex 选择了 {target_name}",
        ],
    }


def human_approval(state: HubState) -> HubState:
    decision = interrupt(
        {
            "type": "prompt_approval",
            "target": state["target"],
            "prompt": state["proposed_prompt"],
        }
    )
    if decision["action"] == "reject":
        return {
            "status": "rejected",
            "timeline": [f"{now()}  你已拒绝这条指令"],
        }
    return {
        "approved_prompt": decision["prompt"],
        "status": "approved",
        "timeline": [f"{now()}  你已批准指令"],
    }


def route_after_approval(state: HubState) -> Literal["dispatch", "__end__"]:
    return "dispatch" if state["status"] == "approved" else END


def dispatch_placeholder(state: HubState) -> HubState:
    target_name = "Claude Code" if state["target"] == "claude" else "WorkBuddy"
    return {
        "status": "ready_to_connect",
        "execution_result": (
            f"{target_name} 的图形化审批流程已经跑通。\n\n"
            "目前这一版不会真的把指令发给执行器，以免在桥接方式尚未确认时误操作。"
            "下一步接入对应适配器后，这里会显示实时回复。"
        ),
        "timeline": [f"{now()}  指令已通过审批，等待连接 {target_name} 适配器"],
    }


def build_graph():
    graph = StateGraph(HubState)
    graph.add_node("prepare_prompt", prepare_prompt)
    graph.add_node("human_approval", human_approval)
    graph.add_node("dispatch", dispatch_placeholder)
    graph.add_edge(START, "prepare_prompt")
    graph.add_edge("prepare_prompt", "human_approval")
    graph.add_conditional_edges("human_approval", route_after_approval)
    graph.add_edge("dispatch", END)
    return graph.compile(checkpointer=InMemorySaver())


class AgentHub(tk.Tk):
    COLORS = {
        "bg": "#111827",
        "panel": "#1f2937",
        "panel_2": "#263244",
        "text": "#f8fafc",
        "muted": "#9ca3af",
        "accent": "#8b5cf6",
        "accent_hover": "#7c3aed",
        "green": "#10b981",
        "red": "#ef4444",
        "border": "#374151",
    }

    def __init__(self) -> None:
        super().__init__()
        self.title("Agent Hub · LangGraph")
        self.geometry("1180x760")
        self.minsize(980, 660)
        self.configure(bg=self.COLORS["bg"])

        self.graph = build_graph()
        self.thread_id: str | None = None
        self.config: dict | None = None
        self.last_state: HubState = {}
        self._planner_result_event: dict | None = None

        self._configure_styles()
        self._build_ui()
        self._set_status("等待你创建任务")

    def _configure_styles(self) -> None:
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure(
            "Hub.TCombobox",
            fieldbackground=self.COLORS["panel_2"],
            background=self.COLORS["panel_2"],
            foreground=self.COLORS["text"],
            arrowcolor=self.COLORS["text"],
            bordercolor=self.COLORS["border"],
            padding=8,
        )

    def _label(self, parent, text: str, size=11, bold=False, color=None):
        return tk.Label(
            parent,
            text=text,
            bg=parent.cget("bg"),
            fg=color or self.COLORS["text"],
            font=("Microsoft YaHei UI", size, "bold" if bold else "normal"),
            anchor="w",
        )

    def _button(self, parent, text: str, command, color: str, width=14):
        return tk.Button(
            parent,
            text=text,
            command=command,
            width=width,
            bg=color,
            fg="white",
            activebackground=color,
            activeforeground="white",
            relief="flat",
            borderwidth=0,
            cursor="hand2",
            font=("Microsoft YaHei UI", 10, "bold"),
            padx=12,
            pady=9,
        )

    def _text_box(self, parent, height=10):
        return tk.Text(
            parent,
            height=height,
            wrap="word",
            undo=True,
            bg=self.COLORS["panel_2"],
            fg=self.COLORS["text"],
            insertbackground=self.COLORS["text"],
            selectbackground=self.COLORS["accent"],
            relief="flat",
            borderwidth=0,
            padx=12,
            pady=10,
            font=("Microsoft YaHei UI", 10),
        )

    def _build_ui(self) -> None:
        header = tk.Frame(self, bg=self.COLORS["bg"], padx=24, pady=18)
        header.pack(fill="x")
        self._label(header, "Agent Hub", 22, True).pack(side="left")
        self._label(
            header,
            "LangGraph 人工审批控制台",
            11,
            color=self.COLORS["muted"],
        ).pack(side="left", padx=(14, 0), pady=(8, 0))
        self.status_label = self._label(
            header, "", 10, True, color=self.COLORS["green"]
        )
        self.status_label.pack(side="right", pady=(8, 0))

        body = tk.Frame(self, bg=self.COLORS["bg"], padx=20, pady=0)
        body.pack(fill="both", expand=True)
        body.grid_columnconfigure(0, weight=1)
        body.grid_columnconfigure(1, weight=1)
        body.grid_columnconfigure(2, weight=1)
        body.grid_rowconfigure(0, weight=1)

        left = self._panel(body, "① Codex 任务")
        middle = self._panel(body, "② 指令审批")
        right = self._panel(body, "③ 执行节点")
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 7))
        middle.grid(row=0, column=1, sticky="nsew", padx=7)
        right.grid(row=0, column=2, sticky="nsew", padx=(7, 0))

        self._label(left, "要完成什么？", 10, True).pack(fill="x", padx=16)
        self.task_text = self._text_box(left, height=12)
        self.task_text.pack(fill="both", expand=True, padx=16, pady=(8, 14))
        self.task_text.insert(
            "1.0", "例如：检查当前项目的结构，并给出下一步实施建议。"
        )

        self._label(left, "交给哪个执行节点？", 10, True).pack(fill="x", padx=16)
        self.target_combo = ttk.Combobox(
            left,
            style="Hub.TCombobox",
            state="readonly",
            values=["由 Codex 决定", "Claude Code", "WorkBuddy"],
        )
        self.target_combo.current(0)
        self.target_combo.pack(fill="x", padx=16, pady=(8, 14))
        self.generate_button = self._button(
            left, "生成待审批指令", self.start_task, self.COLORS["accent"], 18
        )
        self.generate_button.pack(anchor="w", padx=16, pady=(0, 16))

        self._label(
            middle,
            "你可以在发送前直接修改下面的内容。",
            9,
            color=self.COLORS["muted"],
        ).pack(fill="x", padx=16)
        self.prompt_text = self._text_box(middle, height=18)
        self.prompt_text.pack(fill="both", expand=True, padx=16, pady=(8, 14))
        approval_buttons = tk.Frame(middle, bg=self.COLORS["panel"])
        approval_buttons.pack(fill="x", padx=16, pady=(0, 16))
        self.approve_button = self._button(
            approval_buttons,
            "批准",
            self.approve,
            self.COLORS["green"],
            10,
        )
        self.approve_button.pack(side="left")
        self.reject_button = self._button(
            approval_buttons,
            "拒绝",
            self.reject,
            self.COLORS["red"],
            10,
        )
        self.reject_button.pack(side="left", padx=(10, 0))

        self._label(right, "执行结果", 10, True).pack(fill="x", padx=16)
        self.result_text = self._text_box(right, height=11)
        self.result_text.pack(fill="both", expand=True, padx=16, pady=(8, 14))
        self.result_text.configure(state="disabled")
        self._label(right, "调用时间线", 10, True).pack(fill="x", padx=16)
        self.timeline = tk.Listbox(
            right,
            height=9,
            bg=self.COLORS["panel_2"],
            fg=self.COLORS["text"],
            selectbackground=self.COLORS["accent"],
            relief="flat",
            borderwidth=0,
            highlightthickness=0,
            font=("Microsoft YaHei UI", 9),
        )
        self.timeline.pack(fill="both", expand=True, padx=16, pady=(8, 16))

        self.approve_button.configure(state="disabled")
        self.reject_button.configure(state="disabled")

    def _panel(self, parent, title: str):
        panel = tk.Frame(
            parent,
            bg=self.COLORS["panel"],
            highlightbackground=self.COLORS["border"],
            highlightthickness=1,
        )
        self._label(panel, title, 13, True).pack(fill="x", padx=16, pady=16)
        return panel

    def _set_status(self, text: str, color: str | None = None) -> None:
        self.status_label.configure(text=f"● {text}", fg=color or self.COLORS["green"])

    def _replace_text(self, widget: tk.Text, value: str, disabled=False) -> None:
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", value)
        if disabled:
            widget.configure(state="disabled")

    def _refresh_timeline(self, state: HubState) -> None:
        self.timeline.delete(0, "end")
        for item in state.get("timeline", []):
            self.timeline.insert("end", item)

    def _format_plan(self, state: HubState) -> str:
        target_name = "Claude Code" if state.get("target") == "claude" else "WorkBuddy"
        steps = "\n".join(
            f"{index}. {step}"
            for index, step in enumerate(state.get("plan_steps", []), start=1)
        )
        criteria = "\n".join(
            f"• {item}" for item in state.get("success_criteria", [])
        )
        return (
            f"Codex 对任务的理解\n{state.get('plan_summary', '')}\n\n"
            f"选择的执行节点\n{target_name}\n\n"
            f"选择理由\n{state.get('target_reason', '')}\n\n"
            f"执行步骤\n{steps}\n\n"
            f"验收标准\n{criteria}"
        )

    def _drain_planner_events(self) -> None:
        while True:
            try:
                event = PLANNER_EVENTS.get_nowait()
            except queue.Empty:
                break
            text = f"{event['time']}  {event['text']}"
            self.timeline.insert("end", text)
            self.timeline.see("end")
            if event["kind"] == "error":
                self._set_status(event["text"], self.COLORS["red"])
            else:
                self._set_status(event["text"], "#f59e0b")

    def _save_event(self, action: str, state: HubState) -> None:
        if not self.thread_id:
            return
        record = {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "thread_id": self.thread_id,
            "action": action,
            "state": state,
        }
        with (LOG_DIR / f"{self.thread_id}.jsonl").open(
            "a", encoding="utf-8"
        ) as file:
            file.write(json.dumps(record, ensure_ascii=False) + "\n")

    def start_task(self) -> None:
        task = self.task_text.get("1.0", "end").strip()
        if not task:
            messagebox.showinfo("还差一步", "请先填写要完成的任务。")
            return

        self.thread_id = str(uuid.uuid4())
        self.config = {"configurable": {"thread_id": self.thread_id}}
        target = ["auto", "claude", "workbuddy"][self.target_combo.current()]
        self.timeline.delete(0, "end")
        self._replace_text(self.prompt_text, "")
        self._replace_text(
            self.result_text,
            "Codex 正在读取任务并制定计划，请稍候……",
            disabled=True,
        )
        self.approve_button.configure(state="disabled")
        self.reject_button.configure(state="disabled")
        self.generate_button.configure(state="disabled")
        self._set_status("Codex 正在启动", "#f59e0b")
        self._planner_result_event = None

        worker = threading.Thread(
            target=self._run_planner_worker,
            args=(task, target),
            daemon=True,
        )
        worker.start()
        self.after(100, self._poll_planner_worker, worker)

    def _run_planner_worker(self, task: str, target: str) -> None:
        try:
            result = self.graph.invoke(
                {"task": task, "target": target, "timeline": []},
                config=self.config,
            )
            PLANNER_EVENTS.put({"kind": "result", "state": result})
        except Exception as exc:
            PLANNER_EVENTS.put({"kind": "exception", "error": str(exc)})

    def _poll_planner_worker(self, worker: threading.Thread) -> None:
        result_event = None
        while True:
            try:
                event = PLANNER_EVENTS.get_nowait()
            except queue.Empty:
                break
            if event["kind"] in {"result", "exception"}:
                self._planner_result_event = event
                continue
            text = f"{event['time']}  {event['text']}"
            self.timeline.insert("end", text)
            self.timeline.see("end")
            self._set_status(
                event["text"],
                self.COLORS["red"] if event["kind"] == "error" else "#f59e0b",
            )

        if worker.is_alive():
            self.after(150, self._poll_planner_worker, worker)
            return

        self.generate_button.configure(state="normal")
        result_event = self._planner_result_event
        self._planner_result_event = None
        if not result_event:
            self._set_status("规划进程意外结束", self.COLORS["red"])
            return
        if result_event["kind"] == "exception":
            error = result_event["error"]
            self._replace_text(self.result_text, error, disabled=True)
            self._set_status("Codex 规划失败", self.COLORS["red"])
            messagebox.showerror("Codex 规划失败", error)
            return

        result = result_event["state"]
        self.last_state = result

        interrupts = result.get("__interrupt__", ())
        if interrupts:
            prompt = interrupts[0].value["prompt"]
            self._replace_text(self.prompt_text, prompt)
            self.approve_button.configure(state="normal")
            self.reject_button.configure(state="normal")
            self._set_status("等待你的审批", "#f59e0b")

        self._replace_text(self.result_text, self._format_plan(result), disabled=True)
        self._refresh_timeline(result)
        self._save_event("task_created", result)

    def approve(self) -> None:
        if not self.config:
            return
        edited_prompt = self.prompt_text.get("1.0", "end").strip()
        if not edited_prompt:
            messagebox.showinfo("无法批准", "指令内容不能为空。")
            return
        result = self.graph.invoke(
            Command(resume={"action": "approve", "prompt": edited_prompt}),
            config=self.config,
        )
        self.last_state = result
        self._replace_text(
            self.result_text, result.get("execution_result", ""), disabled=True
        )
        self._refresh_timeline(result)
        self.approve_button.configure(state="disabled")
        self.reject_button.configure(state="disabled")
        self._set_status("审批完成，等待接入执行器")
        self._save_event("approved", result)

    def reject(self) -> None:
        if not self.config:
            return
        result = self.graph.invoke(
            Command(resume={"action": "reject", "prompt": ""}),
            config=self.config,
        )
        self.last_state = result
        self._replace_text(self.result_text, "这条指令已被你拒绝。", disabled=True)
        self._refresh_timeline(result)
        self.approve_button.configure(state="disabled")
        self.reject_button.configure(state="disabled")
        self._set_status("已拒绝", self.COLORS["red"])
        self._save_event("rejected", result)


if __name__ == "__main__":
    AgentHub().mainloop()
