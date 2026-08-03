#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据分析脚本自测。

功能: 用 samples 下的两个样例 CSV 验证 analyze.py 的三个子命令输出符合预期,
     确认字段类型识别、统计量、异常检测、频次计算正确且不崩溃。
创建日期: 2026-08-03

输入: samples/销售明细.csv(数值/日期/分类/含异常值), samples/客户分布.csv(全分类)。
输出: 控制台打印每项断言结果; 全部通过返回 exit 0,否则 exit 1。
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
SCRIPT = os.path.join(ROOT, "scripts", "analyze.py")
SALES = os.path.join(ROOT, "samples", "销售明细.csv")
CUSTOMER = os.path.join(ROOT, "samples", "客户分布.csv")

PY = sys.executable


def run(cmd, path):
    """运行 analyze.py 子命令并返回解析后的 JSON。"""
    out = subprocess.run(
        [PY, SCRIPT, cmd, path], capture_output=True, text=True, encoding="utf-8"
    )
    if out.returncode != 0:
        print(f"[FAIL] 子命令 {cmd} 退出码 {out.returncode}: {out.stderr}")
        return None
    try:
        return json.loads(out.stdout)
    except json.JSONDecodeError:
        print(f"[FAIL] 子命令 {cmd} 输出非 JSON: {out.stdout[:200]}")
        return None


PASS = 0
FAIL = 0


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
    print("excel-insight-analyzer 自测开始")
    print("=" * 60)

    # ---- 销售明细: profile ----
    prof = run("profile", SALES)
    if prof:
        check("profile: 销售明细行数=34", prof["rows"] == 34, f"实际 {prof['rows']}")
        check("profile: 字段数=8", prof["cols"] == 8, f"实际 {prof['cols']}")
        t = prof["types"]
        check("profile: 订单日期为date", t.get("订单日期") == "date", str(t.get("订单日期")))
        check("profile: 销售额为numeric", t.get("销售额") == "numeric", str(t.get("销售额")))
        check("profile: 地区为category", t.get("地区") == "category", str(t.get("地区")))
        check("profile: 商品类目为category", t.get("商品类目") == "category", str(t.get("商品类目")))
        # 订单号唯一值=行数,应归 category(不当 numeric)
        check("profile: 订单号不当numeric(归category)",
              t.get("订单号") != "numeric", str(t.get("订单号")))

    # ---- 销售明细: stats ----
    st = run("stats", SALES)
    if st:
        pf = st["per_field"]
        check("stats: 含销售额统计", "销售额" in pf)
        check("stats: 销售额count=34", pf.get("销售额", {}).get("count") == 34,
              str(pf.get("销售额", {}).get("count")))
        # 销售额里有 12000 这条极端异常(行31)和 0 这条(行30)
        ol = st["outliers"].get("销售额", [])
        rows = [o["row"] for o in ol]
        check("stats: 销售额检出异常(含行31的12000)", 31 in rows, str(rows))
        high = [o for o in ol if o["confidence"] == "high"]
        check("stats: 至少1个高置信异常", len(high) >= 1, str(high))
        # 数值字段不应把订单号算进来
        check("stats: 订单号未被当数值统计", "订单号" not in pf)

    # ---- 销售明细: freq ----
    fq = run("freq", SALES)
    if fq:
        per = fq["per_field"]
        check("freq: 含地区频次", "地区" in per)
        check("freq: 地区unique=4", per.get("地区", {}).get("unique") == 4,
              str(per.get("地区", {}).get("unique")))
        check("freq: 销售额(数值)不进freq", "销售额" not in per)

    # ---- 客户分布: 全分类 ----
    st2 = run("stats", CUSTOMER)
    if st2:
        check("stats: 客户分布无数值字段(per_field为空)", st2["per_field"] == {},
              str(st2["per_field"]))
        check("stats: 客户分布无异常(outliers为空)", st2["outliers"] == {},
              str(st2["outliers"]))
    fq2 = run("freq", CUSTOMER)
    if fq2:
        per2 = fq2["per_field"]
        check("freq: 客户分布含会员等级", "会员等级" in per2)
        check("freq: 会员等级unique=3", per2.get("会员等级", {}).get("unique") == 3,
              str(per2.get("会员等级", {}).get("unique")))

    # ---- 异常输入不崩溃 ----
    err = run("profile", os.path.join(ROOT, "samples", "不存在的文件.csv"))
    check("异常: 文件不存在返回error且不崩溃",
          err is not None and "error" in err, str(err))

    # ---- sanitize_cell 基本检查 ----
    sys.path.insert(0, os.path.join(ROOT, "scripts"))
    import analyze  # noqa
    s = analyze.sanitize_cell("a|b<c>\n=d")
    check("sanitize: 转义管道符与尖括号",
          "\\|" in s and "&lt;" in s and "&gt;" in s and "&amp;lt;" not in s, s)
    check("sanitize: 公式注入前置单引号",
          analyze.sanitize_cell("=cmd").startswith("'"), analyze.sanitize_cell("=cmd"))

    print("=" * 60)
    print(f"自测结束: 通过 {PASS} 项, 失败 {FAIL} 项")
    print("=" * 60)
    sys.exit(0 if FAIL == 0 else 1)


if __name__ == "__main__":
    main()
