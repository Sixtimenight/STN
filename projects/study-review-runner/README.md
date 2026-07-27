# Study Review Runner

一个从 Word 题库中抽取复习题并保存轮转进度的本地小工具。

## 功能

- 从 `.docx` 读取章节、题号、题目和答案
- 未安装 `python-docx` 时直接读取 DOCX 内部 XML
- 按固定顺序循环抽题，避免纯随机造成重复和遗漏
- 可按规则跳过每章最后一题
- 使用 JSON 保存下次起点和最近 30 次运行历史
- 支持自定义每次抽题数量

## 题库格式

```text
第一章
1-1 题目内容
答案内容
1-2 下一道题
答案内容
```

把题库命名为包含“复习题”的 `.docx` 文件，并与脚本放在同一目录。

## 安装

脚本可以只使用 Python 标准库运行；安装 `python-docx` 后，对 Word 文档的兼容性更好。

```powershell
python -m pip install -r requirements.txt
```

## 使用

```powershell
python review_task_runner.py draw --count 5
```

运行后会在同一目录生成 `review_task_state.json`。该状态文件和真实题库默认不会提交到 GitHub。

