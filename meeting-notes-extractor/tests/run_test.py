#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
会议纪要脚本自测。

功能: 验证 notes_gen.py 的 parse/extract,确认发言人识别、待办候选、
     时间表达抽取正确,不崩溃。
创建日期: 2026-08-03
"""

import sys
import os
import json
import subprocess

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SCRIPT = os.path.join(ROOT, "scripts", "notes_gen.py")
SAMPLE = os.path.join(ROOT, "samples", "会议转写-产品评审.txt")
PY = sys.executable

PASS = 0
FAIL = 0


def run(cmd, path):
    out = subprocess.run([PY, SCRIPT, cmd, path], capture_output=True, text=True, encoding="utf-8")
    if out.returncode != 0:
        print(f"[FAIL] {cmd} 退出码 {out.returncode}: {out.stderr}")
        return None
    try:
        return json.loads(out.stdout)
    except json.JSONDecodeError:
        print(f"[FAIL] {cmd} 输出非 JSON: {out.stdout[:200]}")
        return None


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"[PASS] {name}")
    else:
        FAIL += 1
        print(f"[FAIL] {name}  {detail}")


def main():
    print("=" * 60)
    print("meeting-notes-extractor 自测开始")
    print("=" * 60)

    # ---- parse ----
    p = run("parse", SAMPLE)
    if p:
        check("parse: 识别到发言人", p["total_turns"] > 0, str(p["total_turns"]))
        names = [s["name"] for s in p["speakers"]]
        check("parse: 含张三", "张三" in names, str(names))
        check("parse: 含李四", "李四" in names, str(names))
        check("parse: 含王五", "王五" in names, str(names))
        check("parse: 含赵六", "赵六" in names, str(names))
        check("parse: 有发言人标签", p["has_speaker_tags"] is True, str(p["has_speaker_tags"]))

    # ---- extract ----
    e = run("extract", SAMPLE)
    if e:
        ac = e["action_candidates"]
        check("extract: 待办候选>=3条", len(ac) >= 3, str(len(ac)))
        # 应含带责任人和截止的待办
        full = [a for a in ac if a["owner"] and a["due"]]
        check("extract: 至少2条待办同时有责任人和截止", len(full) >= 2, str(len(full)))
        # 关键内容校验:应命中"本周五"(前端联调)
        all_kw = [k for a in ac for k in a["keyword"]]
        check("extract: 命中负责/跟进类关键词", any(k in ("负责", "跟进", "牵头") for k in all_kw), str(all_kw))
        # 时间表达
        te = e["time_expressions"]
        check("extract: 含本周五", "本周五" in te, str(te))
        check("extract: 含下周三", any("下周三" in t for t in te), str(te))
        check("extract: 含8月10号", any("8月10" in t for t in te), str(te))

    # ---- 无发言人标签的纯文本 ----
    plain = run("parse", "今天讨论了需求，决定下周五交付。张三负责前端。")
    if plain is not None:
        check("parse: 纯文本无标签不崩溃", "total_turns" in plain, str(plain))

    # ---- sanitize ----
    sys.path.insert(0, os.path.join(ROOT, "scripts"))
    import notes_gen  # noqa
    sv = notes_gen.sanitize_cell("a|b<c>&=d")
    check("sanitize: 转义", "\\|" in sv and "&lt;" in sv and "&amp;" in sv and "&amp;lt;" not in sv, sv)

    # ---- 异常输入 ----
    ee = run("extract", "")
    check("异常: 空文本不崩溃", ee is not None, str(ee))

    print("=" * 60)
    print(f"自测结束: 通过 {PASS} 项, 失败 {FAIL} 项")
    print("=" * 60)
    sys.exit(0 if FAIL == 0 else 1)


if __name__ == "__main__":
    main()
