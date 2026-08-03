#!/usr/bin/env python3
"""
公文智能处理助手 —— 自动化自测脚本。

功能: 对四个模块用 samples/ 下的样例做端到端验证,打印预期与实际结果,供评审一键验证。
创建日期: 2026-08-02

输入: 无(脚本自动定位 samples/ 与 scripts/gongwen_toolkit.py)。
输出: 控制台打印各模块测试结论(PASS/FAIL),退出码 0 表示全部通过。
"""

import os
import sys
from pathlib import Path

if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# 定位项目根目录(Skill 根, 即 tests/ 的上一级)
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
SAMPLES = ROOT / "samples"

import gongwen_toolkit as gt  # noqa: E402


def sep(title):
    print("\n" + "=" * 60)
    print(f"  测试：{title}")
    print("=" * 60)


def test_check_wrong():
    """模块①：含错样例应报出 ≥3 个问题，且至少含发文字号/日期/层次序号错误。"""
    sep("模块① 格式校验 —— 含错样例")
    text = gt.read_text(str(SAMPLES / "校验-含错.txt"))
    issues = gt.check_gongwen(text)
    print(f"实际问题数: {len(issues)}")
    for it in issues:
        print(f"  [{it['level']}] {it['desc']}")
    descs = " ".join(it["desc"] for it in issues)
    cond_count = len(issues) >= 3
    cond_bracket = "六角括号" in descs
    cond_date = "成文日期" in descs or "中文数字" in descs
    cond_level = "层次序号" in descs or "阿拉伯数字" in descs
    passed = cond_count and (cond_bracket or cond_date or cond_level)
    print(f"\n断言: 问题数≥3({cond_count}) 含括号错误({cond_bracket}) "
          f"含日期错误({cond_date}) 含序号错误({cond_level})")
    print("结论:", "✅ PASS" if passed else "❌ FAIL")
    return passed


def test_check_correct():
    """模块①：合规样例应报 0 个严重问题。"""
    sep("模块① 格式校验 —— 合规样例")
    text = gt.read_text(str(SAMPLES / "校验-合规.txt"))
    issues = gt.check_gongwen(text)
    severe = [i for i in issues if i["level"] == "严重"]
    print(f"问题数: {len(issues)}(其中严重 {len(severe)})")
    for it in severe:
        print(f"  [严重] {it['desc']}")
    passed = len(severe) == 0
    print("断言: 合规样例严重问题数=0")
    print("结论:", "✅ PASS" if passed else "❌ FAIL")
    return passed


def test_extract():
    """模块②：对来文样例应抽出 ≥3 个要素。"""
    """模块③：对来文样例应抽出 ≥3 个要素。"""
    sep("模块③ 关键信息提取 —— 来文样例")
    text = gt.read_text(str(SAMPLES / "提取-来文.txt"))
    info = gt.extract_info(text)
    print("提取结果:")
    for k, v in info.items():
        print(f"  {k}: {v}")
    non_empty = sum(1 for v in info.values() if v)
    passed = non_empty >= 3
    print(f"\n断言: 非空要素数≥3(实际 {non_empty})")
    print("结论:", "✅ PASS" if passed else "❌ FAIL")
    return passed


def test_glossary():
    """模块④：术语样例应识别出 ≥2 处不规范术语。"""
    sep("模块④ 规范术语校正 —— 术语样例")
    text = gt.read_text(str(SAMPLES / "校验-术语.txt"))
    results = gt.glossary_check(text)
    print(f"识别不规范术语: {len(results)} 处")
    for r in results:
        print(f"  行{r['line']}: 「{r['bad']}」 → 「{r['good']}」")
    passed = len(results) >= 2
    print(f"\n断言: 不规范术语≥2 处(实际 {len(results)})")
    print("结论:", "✅ PASS" if passed else "❌ FAIL")
    return passed


def test_sanitize():
    """安全函数：sanitize_cell 应正确处理注入字符。"""
    sep("安全函数 sanitize_cell 注入防护")
    cases = [
        ("a|b", "管道符转义"),
        ("a\nb", "换行去除"),
        ("a<b>c", "尖括号转义"),
        ("=cmd", "公式前缀加单引号"),
        ("![](x)", "图片语法降级"),
        ("javascript:alert", "协议拆开"),
    ]
    all_ok = True
    for inp, desc in cases:
        out = gt.sanitize_cell(inp)
        ok = ("|" not in out or "\\|" in out) and "\n" not in out
        ok = ok and (not out.startswith("=")) and (not out.startswith("!"))
        ok = ok and ("javascript:" not in out)
        print(f"  {desc}: 「{inp}」 → 「{out}」 {'✅' if ok else '❌'}")
        all_ok = all_ok and ok
    print("结论:", "✅ PASS" if all_ok else "❌ FAIL")
    return all_ok


def test_real_pdf_sample():
    """回归测试: 用真实 PDF 抽取的公文(武汉城市更新通知)验证发文字号/日期/序号识别。

    防止 normalize_spaces 或正则改动导致 PDF 多空格场景下漏抽。
    """
    sep("真实样例(PDF抽取) —— 武汉城市更新通知")
    path = SAMPLES / "真实样例-武汉城市更新通知.txt"
    if not path.exists():
        print("⚠️ 真实样例不存在,跳过")
        return True
    text = gt.read_text(str(path))
    info = gt.extract_info(text)
    print(f"  发文字号: {info['发文字号']}")
    print(f"  成文日期: {info['成文日期']}")
    ok_fawen = "武政办〔2025〕115号" == info["发文字号"]
    ok_date = "2025年12月22日" == info["成文日期"]
    # 同时验证 check 模块不再误报"未识别发文字号/日期"
    issues = gt.check_gongwen(text)
    desc_join = " ".join(i["desc"] for i in issues)
    ok_no_false = ("未识别到发文字号" not in desc_join
                   and "未识别到成文日期" not in desc_join)
    # 验证半角括号漏报已修复
    ok_halfwidth = any("半角圆括号" in i["desc"] for i in issues)
    passed = ok_fawen and ok_date and ok_no_false and ok_halfwidth
    print(f"\n断言: 发文字号准({ok_fawen}) 日期准({ok_date}) "
          f"无误报({ok_no_false}) 半角括号已报({ok_halfwidth})")
    print("结论:", "✅ PASS" if passed else "❌ FAIL")
    return passed


def main():
    results = {
        "校验-含错": test_check_wrong(),
        "校验-合规": test_check_correct(),
        "信息提取": test_extract(),
        "术语校正": test_glossary(),
        "注入防护": test_sanitize(),
        "真实PDF样例": test_real_pdf_sample(),
    }
    sep("总览")
    for name, ok in results.items():
        print(f"  {name}: {'✅ PASS' if ok else '❌ FAIL'}")
    n_pass = sum(results.values())
    print(f"\n通过: {n_pass}/{len(results)}")
    sys.exit(0 if n_pass == len(results) else 1)


if __name__ == "__main__":
    main()
