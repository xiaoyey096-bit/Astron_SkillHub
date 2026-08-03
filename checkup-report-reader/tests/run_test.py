#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""体检报告解读脚本自测。验证 health_check.py parse/compare。创建日期: 2026-08-03"""
import sys, os, json, subprocess
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SCRIPT = os.path.join(ROOT, "scripts", "health_check.py")
SAMPLE = os.path.join(ROOT, "samples", "体检报告样例.txt")
PY = sys.executable
PASS = FAIL = 0


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
    print("checkup-report-reader 自测开始")
    print("=" * 60)

    pr = run("parse", SAMPLE)
    if pr:
        names = [it["name"] for it in pr["items"]]
        check("parse: 解析到总胆固醇", "总胆固醇" in names, str(names))
        check("parse: 解析到低密度脂蛋白", "低密度脂蛋白" in names, str(names))
        check("parse: 解析到空腹血糖", "空腹血糖" in names, str(names))
        check("parse: 解析到谷丙转氨酶", "谷丙转氨酶" in names, str(names))
        check("parse: 解析项数>=8", pr["count"] >= 8, str(pr["count"]))

    cp = run("compare", SAMPLE)
    if cp:
        items = {it["name"]: it for it in cp["items"]}
        # 总胆固醇6.8 > 5.2, 偏离30%+, 应red
        tc = items.get("总胆固醇", {})
        check("compare: 总胆固醇偏高", tc.get("status") == "high", str(tc))
        check("compare: 总胆固醇判red(偏离大)", tc.get("severity") == "red", str(tc.get("severity")))
        # 低密度4.2>3.4, 偏离约24%, red
        ldl = items.get("低密度脂蛋白", {})
        check("compare: 低密度偏高", ldl.get("status") == "high", str(ldl))
        # 空腹血糖6.8, 关键指标, 偏离>10%, red
        glu = items.get("空腹血糖", {})
        check("compare: 空腹血糖偏高", glu.get("status") == "high", str(glu))
        check("compare: 空腹血糖关键指标判red", glu.get("severity") == "red", str(glu))
        # 高密度1.1在正常(>1.04), 且偏高有益, 不应报异常
        hdl = items.get("高密度脂蛋白", {})
        check("compare: 高密度正常(偏高有益不报)", hdl.get("severity") == "green", str(hdl))
        # ALT35<40 正常
        alt = items.get("谷丙转氨酶", {})
        check("compare: ALT正常", alt.get("severity") == "green", str(alt))
        # 收缩压128<139 正常
        sbp = items.get("收缩压", {})
        check("compare: 收缩压正常", sbp.get("severity") == "green", str(sbp))
        # 有counts
        check("compare: 有counts统计", "counts" in cp, str(cp.get("counts")))
        # 至少2个非green
        non_green = sum(1 for it in cp["items"] if it["severity"] != "green")
        check("compare: 至少2项异常", non_green >= 2, str(non_green))

    # ---- sanitize ----
    sys.path.insert(0, os.path.join(ROOT, "scripts"))
    import health_check  # noqa
    sv = health_check.sanitize_cell("a|b<c>&=d")
    check("sanitize: 转义", "\\|" in sv and "&lt;" in sv and "&amp;" in sv and "&amp;lt;" not in sv, sv)

    # ---- 异常输入 ----
    ee = run("compare", "无有效指标")
    check("异常: 无效输入不崩溃", ee is not None, str(ee))

    print("=" * 60)
    print(f"自测结束: 通过 {PASS} 项, 失败 {FAIL} 项")
    print("=" * 60)
    sys.exit(0 if FAIL == 0 else 1)


if __name__ == "__main__":
    main()
