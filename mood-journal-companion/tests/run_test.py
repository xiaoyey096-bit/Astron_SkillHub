#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
情绪日记分析脚本自测。

功能: 用 samples 下三个样例验证 mood_analyze.py 的四个子命令,
     确认危机筛查、情绪归类、压力源归因、认知识别正确且不崩溃。
创建日期: 2026-08-03

输入: samples/情绪记录-工作压力.txt, 情绪记录-平静日常.txt, 情绪记录-危机信号.txt。
输出: 控制台打印每项断言; 全通过 exit 0,否则 exit 1。
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
SCRIPT = os.path.join(ROOT, "scripts", "mood_analyze.py")
S_WORK = os.path.join(ROOT, "samples", "情绪记录-工作压力.txt")
S_CALM = os.path.join(ROOT, "samples", "情绪记录-平静日常.txt")
S_CRISIS = os.path.join(ROOT, "samples", "情绪记录-危机信号.txt")
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
    print("mood-journal-companion 自测开始")
    print("=" * 60)

    # ---- 危机样例: crisis 必须 flag=True ----
    cr = run("crisis", S_CRISIS)
    if cr:
        check("crisis: 危机样例 flag=True", cr["flag"] is True, str(cr["flag"]))
        check("crisis: 命中自杀意图类", any("自杀" in h["type"] for h in cr["hits"]), str(cr["hits"]))
    # 非危机样例不应触发
    crw = run("crisis", S_WORK)
    if crw is not None:
        check("crisis: 工作压力样例 flag=False(非危机)", crw["flag"] is False, str(crw["flag"]))
    crc = run("crisis", S_CALM)
    if crc is not None:
        check("crisis: 平静样例 flag=False", crc["flag"] is False, str(crc["flag"]))

    # ---- 工作压力样例: classify ----
    cl = run("classify", S_WORK)
    if cl:
        types = [e["type"] for e in cl["emotions"]]
        check("classify: 工作压力含 anxiety", "anxiety" in types, str(types))
        check("classify: 工作压力含 depression(崩溃/撑不住)", "depression" in types, str(types))
        check("classify: 有主导情绪", cl["dominant"] is not None, str(cl["dominant"]))
        # 焦虑强度应 >=2
        anx = [e for e in cl["emotions"] if e["type"] == "anxiety"]
        if anx:
            check("classify: 焦虑强度>=2", anx[0]["strength"] >= 2, str(anx[0]))
        else:
            check("classify: 焦虑强度>=2", False, "未识别到焦虑")

    # ---- 平静样例: classify 应识别 calm ----
    clc = run("classify", S_CALM)
    if clc:
        types_c = [e["type"] for e in clc["emotions"]]
        check("classify: 平静样例识别 calm", "calm" in types_c, str(types_c))

    # ---- 工作压力样例: stressor ----
    st = run("stressor", S_WORK)
    if st:
        dims = [d["dim"] for d in st["dimensions"]]
        check("stressor: 识别 work_study 维度", "work_study" in dims, str(dims))
        check("stressor: 识别 future_self(什么都做不好)", "future_self" in dims, str(dims))

    # ---- 工作压力样例: cognition ----
    co = run("cognition", S_WORK)
    if co:
        ctypes = [d["type"] for d in co["distortions"]]
        check("cognition: 识别灾难化(完了/搞砸)", "catastrophizing" in ctypes, str(ctypes))
        check("cognition: 识别贴标签(什么都做不好)", "labeling" in ctypes, str(ctypes))

    # ---- 平静样例: cognition 应无明显扭曲 ----
    coc = run("cognition", S_CALM)
    if coc is not None:
        # 平静样例不应有大量扭曲(允许偶发,但应很少)
        check("cognition: 平静样例无明显扭曲(<=1)", len(coc["distortions"]) <= 1, str(coc["distortions"]))

    # ---- 直接文本输入(非文件) ----
    clt = run("classify", "我今天好开心，特别满足")
    if clt:
        check("输入: 支持直接文本(非文件)", clt["dominant"] in ("calm",), str(clt))

    # ---- sanitize ----
    sys.path.insert(0, os.path.join(ROOT, "scripts"))
    import mood_analyze  # noqa
    sv = mood_analyze.sanitize_cell("a|b<c>&=d")
    check("sanitize: 转义", "\\|" in sv and "&lt;" in sv and "&amp;" in sv and "&amp;lt;" not in sv, sv)

    # ---- 异常输入不崩溃 ----
    # 空文本
    cle = run("classify", "")
    check("异常: 空文本不崩溃(返回空emotions)", cle is not None and cle.get("emotions") == [], str(cle))

    print("=" * 60)
    print(f"自测结束: 通过 {PASS} 项, 失败 {FAIL} 项")
    print("=" * 60)
    sys.exit(0 if FAIL == 0 else 1)


if __name__ == "__main__":
    main()
