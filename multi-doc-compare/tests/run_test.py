#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""多文档对比脚本自测。验证 doc_compare.py parse/matrix/diff。创建日期: 2026-08-03"""
import sys, os, json, subprocess
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SCRIPT = os.path.join(ROOT, "scripts", "doc_compare.py")
SAMPLE = os.path.join(ROOT, "samples", "产品对比样例.txt")
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
    print("multi-doc-compare 自测开始")
    print("=" * 60)

    pr = run("parse", SAMPLE)
    if pr:
        check("parse: 切分出3份文档", pr["doc_count"] == 3, str(pr["doc_count"]))
        names = [d["name"] for d in pr["docs"]]
        # name 取分隔符标签(文档A/B/C), 产品名在正文里
        check("parse: 含文档A/B/C标签", "文档A" in names and "文档B" in names, str(names))
        # 每份都命中了价格维度
        all_hit_price = all("价格" in d["dims_hit"] for d in pr["docs"])
        check("parse: 三份都命中价格维度", all_hit_price, str([d["dims_hit"] for d in pr["docs"]]))

    mx = run("matrix", SAMPLE)
    if mx:
        check("matrix: 维度并集>=4", len(mx["dimensions"]) >= 4, str(mx["dimensions"]))
        check("matrix: 含价格维度", "价格" in mx["dimensions"], str(mx["dimensions"]))
        check("matrix: 含功能维度", "功能" in mx["dimensions"], str(mx["dimensions"]))
        # 价格行应有3个cell
        price_row = next((r for r in mx["matrix"] if r["dimension"] == "价格"), None)
        if price_row:
            check("matrix: 价格行有3个文档cell", len(price_row["cells"]) == 3, str(price_row["cells"]))
            # 内容非"未提及"
            non_empty = sum(1 for v in price_row["cells"].values() if v != "未提及")
            check("matrix: 价格行3份都有内容", non_empty == 3, str(price_row["cells"]))

    df = run("diff", SAMPLE)
    if df:
        # 共识候选: 功能(都支持Markdown)、平台类(都命中)
        check("diff: 有共识候选", len(df["consensus_candidates"]) >= 1, str(df["consensus_candidates"]))
        # 价格分歧候选(三份价格数值不同)
        cc = df["conflict_candidates"]
        check("diff: 有价格分歧候选", len(cc) >= 2, str(cc))
        # 独有/差异内容候选: 同维度内容差异(如"特色"三份内容不同)
        ddc = df.get("diff_content_candidates", {})
        check("diff: 有差异内容候选(供AI判独有/分歧)", "特色" in ddc or len(ddc) >= 1, str(list(ddc.keys())))

    # ---- 单文档(应提示需多份, 但不崩溃) ----
    single = run("matrix", "只有一份文档的内容，价格10元，功能简单。")
    check("单文档: 不崩溃(返回doc_count)", single is not None and "doc_count" in single, str(single))

    # ---- sanitize ----
    sys.path.insert(0, os.path.join(ROOT, "scripts"))
    import doc_compare  # noqa
    sv = doc_compare.sanitize_cell("a|b<c>&=d")
    check("sanitize: 转义", "\\|" in sv and "&lt;" in sv and "&amp;" in sv and "&amp;lt;" not in sv, sv)

    print("=" * 60)
    print(f"自测结束: 通过 {PASS} 项, 失败 {FAIL} 项")
    print("=" * 60)
    sys.exit(0 if FAIL == 0 else 1)


if __name__ == "__main__":
    main()
