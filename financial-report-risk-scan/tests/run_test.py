#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
金融风险扫描脚本自测。
验证 risk_scan.py 的 extract/risk,确认数据抽取、风险信号识别正确,不崩溃。
创建日期: 2026-08-03
"""
import sys, os, json, subprocess
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SCRIPT = os.path.join(ROOT, "scripts", "risk_scan.py")
S_RISK = os.path.join(ROOT, "samples", "年报样例-含风险.txt")
S_OK = os.path.join(ROOT, "samples", "年报样例-健康.txt")
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
    print("financial-report-risk-scan 自测开始")
    print("=" * 60)

    # ---- 含风险样例 ----
    ex = run("extract", S_RISK)
    if ex:
        check("extract: 识别为年报", ex["doc_type"] == "年报", str(ex["doc_type"]))
        metrics = [f["metric"] for f in ex["financials"]]
        check("extract: 抽到营业收入", "营业收入" in metrics, str(metrics))
        check("extract: 抽到净利润", "净利润" in metrics, str(metrics))
        check("extract: 营收有同比", any(f["metric"] == "营业收入" and f["yoy"] for f in ex["financials"]),
              str(ex["financials"]))

    rk = run("risk", S_RISK)
    if rk:
        names = [s["name"] for s in rk["signals"]]
        check("risk: 识别营收下滑", "营收下滑" in names, str(names))
        check("risk: 识别净利润亏损", "净利润亏损" in names, str(names))
        check("risk: 识别现金流为负", "经营性现金流为负" in names, str(names))
        check("risk: 识别审计非标", "审计非标意见" in names, str(names))
        check("risk: 识别重大诉讼", "重大诉讼" in names, str(names))
        high = [s for s in rk["signals"] if s["severity"] == "high"]
        check("risk: 至少3条高关注", len(high) >= 3, str(len(high)))
        # 资产负债率76%应判high
        debt = [s for s in rk["signals"] if s["name"] == "资产负债率偏高"]
        if debt:
            check("risk: 负债率76%判high", debt[0]["severity"] == "high", str(debt[0]))
        # 每条信号字段完整
        ok = all(all(k in s for k in ("name", "severity", "evidence", "hint")) for s in rk["signals"])
        check("risk: 每条信号字段完整", ok)

    # ---- 健康样例 ----
    rk2 = run("risk", S_OK)
    if rk2:
        high2 = [s for s in rk2["signals"] if s["severity"] == "high"]
        # 健康样例负债率28%,不应报(低负债)
        debt2 = [s for s in rk2["signals"] if s["name"] == "资产负债率偏高"]
        check("risk: 健康样例低负债28%不报", len(debt2) == 0, str(debt2))
        check("risk: 健康样例无高关注信号", len(high2) == 0, str(high2))

    # ---- sanitize ----
    sys.path.insert(0, os.path.join(ROOT, "scripts"))
    import risk_scan  # noqa
    sv = risk_scan.sanitize_cell("a|b<c>&=d")
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
