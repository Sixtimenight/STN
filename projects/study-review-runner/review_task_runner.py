from __future__ import annotations

import argparse
import json
import re
import sys
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable
from xml.etree import ElementTree as ET

try:
    from docx import Document  # type: ignore[import-not-found]
except ModuleNotFoundError:
    Document = None


BASE_DIR = Path(__file__).resolve().parent
DOCX_PATH = next((path for path in BASE_DIR.glob("*.docx") if "复习题" in path.name), BASE_DIR / "复习题.docx")
STATE_PATH = BASE_DIR / "review_task_state.json"
WORD_NAMESPACE = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}


@dataclass
class Question:
    chapter: str
    qid: str
    prompt: str
    answer: str


def is_chapter_heading(text: str) -> bool:
    text = text.strip()
    return bool(re.fullmatch(r"第.+章", text))


def parse_question_start(text: str) -> tuple[str, str] | None:
    parts = text.strip().split(maxsplit=1)
    if len(parts) != 2 or "-" not in parts[0]:
        return None
    left, right = parts[0].split("-", 1)
    if left.isdigit() and right.isdigit():
        return parts[0], parts[1]
    return None


def clean_lines(lines: Iterable[str]) -> str:
    cleaned = [line.strip() for line in lines if line.strip()]
    return "\n".join(cleaned)


def iter_doc_paragraphs(docx_path: Path) -> list[str]:
    if not docx_path.exists():
        raise FileNotFoundError(f"题库文件不存在: {docx_path}")

    if Document is not None:
        doc = Document(str(docx_path))
        return [para.text for para in doc.paragraphs]

    with zipfile.ZipFile(docx_path) as archive:
        xml_bytes = archive.read("word/document.xml")

    root = ET.fromstring(xml_bytes)
    paragraphs: list[str] = []
    for para in root.findall(".//w:p", WORD_NAMESPACE):
        texts = [node.text or "" for node in para.findall(".//w:t", WORD_NAMESPACE)]
        paragraphs.append("".join(texts))
    return paragraphs


def load_questions() -> list[Question]:
    chapter = ""
    current_qid = ""
    current_prompt = ""
    answer_lines: list[str] = []
    questions: list[Question] = []

    def flush_current() -> None:
        nonlocal current_qid, current_prompt, answer_lines
        if current_qid:
            questions.append(
                Question(
                    chapter=chapter,
                    qid=current_qid,
                    prompt=current_prompt,
                    answer=clean_lines(answer_lines),
                )
            )
            current_qid = ""
            current_prompt = ""
            answer_lines = []

    for raw_text in iter_doc_paragraphs(DOCX_PATH):
        text = raw_text.strip()
        if not text:
            continue
        if is_chapter_heading(text):
            flush_current()
            chapter = text
            continue
        parsed = parse_question_start(text)
        if parsed:
            parsed_qid, parsed_prompt = parsed
            if current_qid and parsed_qid == current_qid:
                answer_lines.append(text)
                continue
            flush_current()
            current_qid, current_prompt = parsed_qid, parsed_prompt
            continue
        if current_qid:
            answer_lines.append(text)

    flush_current()
    return questions


def eligible_questions(questions: list[Question]) -> list[Question]:
    by_chapter: dict[str, list[Question]] = {}
    for q in questions:
        by_chapter.setdefault(q.chapter, []).append(q)

    excluded = {items[-1].qid for items in by_chapter.values() if items}
    return [q for q in questions if q.qid not in excluded]


def load_state(total: int) -> dict:
    if STATE_PATH.exists():
        with STATE_PATH.open("r", encoding="utf-8") as fh:
            state = json.load(fh)
    else:
        state = {}
    next_index = state.get("next_index", 0)
    if not isinstance(next_index, int) or next_index < 0 or next_index >= max(total, 1):
        next_index = 0
    history = state.get("history", [])
    if not isinstance(history, list):
        history = []
    return {"next_index": next_index, "history": history}


def save_state(state: dict) -> None:
    with STATE_PATH.open("w", encoding="utf-8") as fh:
        json.dump(state, fh, ensure_ascii=False, indent=2)


def draw_questions(count: int) -> str:
    questions = eligible_questions(load_questions())
    if not questions:
        raise RuntimeError("没有可用题目。")

    state = load_state(len(questions))
    start = state["next_index"]
    picked = [questions[(start + offset) % len(questions)] for offset in range(count)]
    state["next_index"] = (start + count) % len(questions)
    state["history"].append(
        {
            "ran_at": datetime.now().isoformat(timespec="seconds"),
            "question_ids": [q.qid for q in picked],
        }
    )
    state["history"] = state["history"][-30:]
    save_state(state)

    lines = []
    lines.append(f"今天按顺序抽出 {count} 题。当前题库共 {len(questions)} 道可考题，已自动跳过每章最后一题。")
    lines.append("")
    for idx, q in enumerate(picked, start=1):
        lines.append(f"{idx}. [{q.chapter}] {q.qid}")
        lines.append(f"题目：{q.prompt}")
        if q.answer:
            lines.append("原答案：")
            lines.append(q.answer)
        else:
            lines.append("原答案：文档中未识别到单独答案段落。")
        lines.append("")
    lines.append(f"下次将从第 {state['next_index'] + 1} 个可考题继续。")
    return "\n".join(lines).strip()


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["draw"])
    parser.add_argument("--count", type=int, default=5)
    args = parser.parse_args()

    if args.command == "draw":
        print(draw_questions(max(1, args.count)))


if __name__ == "__main__":
    main()
