#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
学习计划脚本自测。

功能: 验证 plan_maker.py 的 breakdown/schedule 子命令,确认能力树匹配、
     时间分配合理(三阶段周数和=总周数、每周任务不超量)且不崩溃。
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
SCRIPT = os.path.join(ROOT, "scripts", "plan_maker.py")
PY = sys.executable

PASS = 0
FAIL = 0


def run(*args):
    out = subprocess.run([PY, SCRIPT] + list(args), capture_output=True, text=True, encoding="utf-8")
    if out.returncode != 0:
        print(f"[FAIL] {' '.join(args)} 退出码 {out.returncode}: {out.stderr}")
        return None
    try:
        return json.loads(out.stdout)
    except json.JSONDecodeError:
        print(f"[FAIL] 输出非 JSON: {out.stdout[:200]}")
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
    print("study-plan-maker 自测开始")
    print("=" * 60)

    # ---- breakdown: 已覆盖目标 ----
    bd = run("breakdown", "python数据分析")
    if bd:
        check("breakdown: 匹配到 Python数据分析", bd.get("matched") is True, str(bd.get("matched")))
        check("breakdown: 有能力模块", len(bd.get("modules", [])) >= 4, str(len(bd.get("modules", []))))
        stages = {m["stage"] for m in bd["modules"]}
        check("breakdown: 含 basic/advanced/practice 三阶段", stages >= {"basic", "advanced", "practice"}, str(stages))
        # 每个模块字段完整
        ok = all(all(k in m for k in ("name", "difficulty", "stage", "resource")) for m in bd["modules"])
        check("breakdown: 每模块字段完整", ok)

    # 模糊匹配
    bd2 = run("breakdown", "数据分析")
    if bd2:
        check("breakdown: 模糊匹配'数据分析'命中", bd2.get("matched") is True, str(bd2.get("matched")))

    # ---- breakdown: 未覆盖目标 ----
    bd3 = run("breakdown", "量子物理")
    if bd3:
        check("breakdown: 未覆盖返回通用模板", bd3.get("matched") is False, str(bd3.get("matched")))
        check("breakdown: 未覆盖有note提示AI拆解", "note" in bd3, str(bd3))

    # ---- schedule: 正常 ----
    sc = run("schedule", "12", "10")
    if sc and "error" not in sc:
        check("schedule: 总周数=12", sc["total_weeks"] == 12, str(sc.get("total_weeks")))
        st = sc["stages"]
        week_sum = st["basic"]["weeks"] + st["advanced"]["weeks"] + st["practice"]["weeks"]
        check("schedule: 三阶段周数和=总周数", week_sum == 12, f"{week_sum} vs 12")
        check("schedule: 每阶段周数>=1", all(st[k]["weeks"] >= 1 for k in st), str({k: st[k]["weeks"] for k in st}))
        check("schedule: 每周有效小时=10*0.9=9.0", abs(sc["effective_weekly_hours"] - 9.0) < 0.01, str(sc["effective_weekly_hours"]))
        check("schedule: 有每周任务上限", sc["tasks_per_week_max"] >= 1, str(sc["tasks_per_week_max"]))
        check("schedule: 缓冲10%", sc["buffer_pct"] == 10, str(sc["buffer_pct"]))

    # ---- schedule: 小周期 ----
    sc2 = run("schedule", "4", "5")
    if sc2 and "error" not in sc2:
        ws = sc2["stages"]["basic"]["weeks"] + sc2["stages"]["advanced"]["weeks"] + sc2["stages"]["practice"]["weeks"]
        check("schedule: 4周三阶段和=4", ws == 4, str(ws))

    # ---- schedule: 异常输入 ----
    sc3 = run("schedule", "abc", "10")
    check("schedule: 非数字返回error", sc3 is not None and "error" in sc3, str(sc3))
    sc4 = run("schedule", "0", "10")
    check("schedule: 0周返回error", sc4 is not None and "error" in sc4, str(sc4))

    # ---- sanitize ----
    sys.path.insert(0, os.path.join(ROOT, "scripts"))
    import plan_maker  # noqa
    sv = plan_maker.sanitize_cell("a|b<c>&=d")
    check("sanitize: 转义", "\\|" in sv and "&lt;" in sv and "&amp;" in sv and "&amp;lt;" not in sv, sv)

    print("=" * 60)
    print(f"自测结束: 通过 {PASS} 项, 失败 {FAIL} 项")
    print("=" * 60)
    sys.exit(0 if FAIL == 0 else 1)


if __name__ == "__main__":
    main()
