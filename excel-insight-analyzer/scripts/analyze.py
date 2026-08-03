#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
表格数据分析脚本（profile / stats / freq 三合一）。

功能: 对 CSV/XLSX 数据表做确定性的统计计算(概览/描述统计/异常检测/频次),
     供 AI 在数据洞察环节调用,保证可复现、不口算出错。
创建日期: 2026-08-03

输入: 命令行参数 <子命令> <文件路径>
  子命令:
    profile <文件>  数据概览(行列数/字段类型/缺失)
    stats   <文件>  数值字段描述统计 + IQR&Zscore 双法异常检测
    freq    <文件>  分类/全部字段频次与占比

输出: 标准 JSON 文本( stdout ),字段含义见各函数注释。
     ① profile  -> rows, cols, types{字段:类型}, missing{字段:缺失数/缺失率}
     ② stats    -> per_field{字段:计数/均值/中位数/std/min/max/Q1/Q3/缺失},
                   outliers{字段:[{row,value,iqr,zscore,confidence}]}
     ③ freq     -> per_field{字段:{unique, top:[{value,count,pct}]}}
"""

import sys
import json
import math
import csv
from collections import Counter

# Windows 控制台 UTF-8 输出,避免 emoji/中文乱码
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


# ---------- 数据读取 ----------

def read_table(path):
    """读取 CSV 或 XLSX 为 (headers, rows)。

    入参: path 文件路径。
    返回: (headers:list[str], rows:list[list[str]]) 单元格均为字符串。
    异常: 文件不存在/格式不支持时抛 ValueError。
    """
    if path.lower().endswith((".xlsx", ".xls")):
        try:
            from openpyxl import load_workbook  # 可选依赖
        except ImportError:
            raise ValueError(
                "读取 xlsx/xls 需要可选依赖 openpyxl,未安装。"
                "请将文件另存为 CSV,或粘贴表格文本后由 AI 落成 CSV。"
            )
        wb = load_workbook(path, read_only=True, data_only=True)
        ws = wb.active
        data = [[("" if c is None else str(c)) for c in row] for row in ws.iter_rows(values_only=True)]
        wb.close()
        if not data:
            return [], []
        width = max(len(r) for r in data)
        data = [r + [""] * (width - len(r)) for r in data]
        return data[0], data[1:]
    # 默认按 CSV 解析(容忍制表符/逗号)
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        sample = f.read(2048)
        f.seek(0)
        delim = "\t" if sample.count("\t") > sample.count(",") else ","
        reader = csv.reader(f, delimiter=delim)
        data = [row for row in reader if any(cell.strip() for cell in row)]
    if not data:
        return [], []
    width = max(len(r) for r in data)
    data = [r + [""] * (width - len(r)) for r in data]
    return data[0], data[1:]


# ---------- 类型识别 ----------

def _is_number(s):
    """判断字符串是否为纯数值(去千分位/百分号/前后空格后)。

    返回: (bool, float|None)。
    """
    if s is None:
        return False, None
    t = str(s).strip()
    if t == "":
        return False, None
    t2 = t.replace(",", "").rstrip("%")
    if t2.endswith("%"):
        return False, None
    try:
        v = float(t2)
        if math.isinf(v) or math.isnan(v):
            return False, None
        return True, v
    except ValueError:
        return False, None


DATE_PATTERNS = [
    # 简化:长度 8/10 的紧凑数字日期 20260803,或带分隔符的日期
]


def _is_date(s):
    """判断字符串是否像日期(常见格式)。返回 bool。"""
    if s is None:
        return False
    t = str(s).strip()
    if t == "":
        return False
    import re
    # 2026-08-03 / 2026/08/03 / 2026.08.03
    if re.match(r"^\d{4}[-/.]\d{1,2}[-/.]\d{1,2}(\s+\d{1,2}:\d{2}(:\d{2})?)?$", t):
        return True
    # 2026年8月3日
    if re.match(r"^\d{4}年\d{1,2}月\d{1,2}日$", t):
        return True
    # 8 位紧凑日期 20260803
    if re.match(r"^\d{8}$", t):
        y, m, d = int(t[:4]), int(t[4:6]), int(t[6:8])
        return 1970 <= y <= 2100 and 1 <= m <= 12 and 1 <= d <= 31
    return False


def infer_types(headers, rows):
    """逐列推断字段类型。

    返回: dict{字段名: 类型},类型为 'numeric'/'date'/'category'/'text'。
    规则参照 references/field-type-rules.md: 数值/日期占非空 >=80% 归该类;
         唯一值<=行数50%且非数值日期归 category;否则 text。
    """
    if not headers or not rows:
        return {h: "text" for h in headers}
    types = {}
    n = len(rows)
    for ci, h in enumerate(headers):
        col = [r[ci] if ci < len(r) else "" for r in rows]
        non_empty = [c for c in col if str(c).strip() != ""]
        if not non_empty:
            types[h] = "text"
            continue
        # 启发式防误判: 字段名含 号/ID/编号/编码/代码 且每行值都不同(=唯一键),
        # 即使全是数字也当归 category(求均值无意义),如订单号、工号、身份证号。
        h_low = str(h).lower()
        is_id_like = any(k in str(h) for k in ("号", "编号", "编码", "代码")) or \
            any(k in h_low for k in ("id", "code", "no"))
        if is_id_like and len(set(non_empty)) == len(non_empty):
            types[h] = "category"
            continue
        # 日期优先于数值(8 位数字可能是日期)
        date_hit = sum(1 for c in non_empty if _is_date(c))
        if date_hit / len(non_empty) >= 0.8:
            types[h] = "date"
            continue
        num_hit = sum(1 for c in non_empty if _is_number(c)[0])
        if num_hit / len(non_empty) >= 0.8:
            types[h] = "numeric"
            continue
        unique = len(set(non_empty))
        if unique <= max(1, n * 0.5):
            types[h] = "category"
        else:
            types[h] = "text"
    return types


# ---------- 子命令: profile ----------

def cmd_profile(path):
    """数据概览:行列数、字段类型、缺失情况。"""
    headers, rows = read_table(path)
    types = infer_types(headers, rows)
    missing = {}
    for ci, h in enumerate(headers):
        col = [r[ci] if ci < len(r) else "" for r in rows]
        miss = sum(1 for c in col if str(c).strip() == "")
        missing[h] = {"missing": miss, "rate": round(miss / len(rows), 4) if rows else 0}
    return {
        "rows": len(rows),
        "cols": len(headers),
        "types": types,
        "missing": missing,
    }


# ---------- 子命令: stats ----------

def _percentile(sorted_vals, p):
    """计算分位数(线性插值)。入参已排序。"""
    if not sorted_vals:
        return None
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    k = (len(sorted_vals) - 1) * p
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return sorted_vals[int(k)]
    return sorted_vals[f] + (sorted_vals[c] - sorted_vals[f]) * (k - f)


def cmd_stats(path):
    """数值字段描述统计 + 异常检测(IQR 与 Z-score 双法)。

    输出:
      per_field{字段: count/mean/median/std/min/max/q1/q3/missing}
      outliers{字段: [{row,value,iqr_hit,zscore_hit,confidence}]}
      confidence: 'high'(双法命中) / 'review'(单法命中)
    """
    headers, rows = read_table(path)
    types = infer_types(headers, rows)
    per_field = {}
    outliers = {}
    for ci, h in enumerate(headers):
        if types.get(h) != "numeric":
            continue
        vals = []  # (row_idx_1based, value)
        miss = 0
        for ri, r in enumerate(rows, start=1):
            c = r[ci] if ci < len(r) else ""
            ok, v = _is_number(c)
            if str(c).strip() == "":
                miss += 1
                continue
            if ok:
                vals.append((ri, v))
            else:
                miss += 1
        if not vals:
            per_field[h] = {"count": 0, "missing": miss}
            continue
        nums = [v for _, v in vals]
        snums = sorted(nums)
        mean = sum(nums) / len(nums)
        median = _percentile(snums, 0.5)
        q1 = _percentile(snums, 0.25)
        q3 = _percentile(snums, 0.75)
        std = math.sqrt(sum((x - mean) ** 2 for x in nums) / len(nums)) if len(nums) > 1 else 0.0
        per_field[h] = {
            "count": len(nums),
            "mean": round(mean, 4),
            "median": round(median, 4) if median is not None else None,
            "std": round(std, 4),
            "min": round(snums[0], 4),
            "max": round(snums[-1], 4),
            "q1": round(q1, 4) if q1 is not None else None,
            "q3": round(q3, 4) if q3 is not None else None,
            "missing": miss,
        }
        # 异常检测
        iqr = (q3 or 0) - (q1 or 0)
        lo = (q1 or 0) - 1.5 * iqr
        hi = (q3 or 0) + 1.5 * iqr
        z_denom = std if std > 0 else None
        ol = []
        for ri, v in vals:
            iqr_hit = v < lo or v > hi
            z_hit = z_denom is not None and abs((v - mean) / z_denom) > 3
            if iqr_hit or z_hit:
                ol.append({
                    "row": ri,
                    "value": round(v, 4),
                    "iqr_hit": iqr_hit,
                    "zscore_hit": z_hit,
                    "confidence": "high" if (iqr_hit and z_hit) else "review",
                })
        if ol:
            outliers[h] = ol
    return {"per_field": per_field, "outliers": outliers}


# ---------- 子命令: freq ----------

def cmd_freq(path):
    """字段频次与占比(分类字段为主,数值字段若唯一值少也统计)。

    输出: per_field{字段: {unique, top:[{value,count,pct}]}}
    """
    headers, rows = read_table(path)
    types = infer_types(headers, rows)
    n = len(rows)
    per_field = {}
    for ci, h in enumerate(headers):
        t = types.get(h)
        if t == "numeric":
            # 数值字段不做频次(除非唯一值很少,这里跳过)
            continue
        col = [str(r[ci]).strip() if ci < len(r) else "" for r in rows]
        col = [c for c in col if c != ""]
        if not col:
            continue
        cnt = Counter(col)
        top = sorted(cnt.items(), key=lambda x: -x[1])[:3]
        per_field[h] = {
            "unique": len(cnt),
            "top": [{"value": v, "count": c, "pct": round(c / n * 100, 1)} for v, c in top],
        }
    return {"per_field": per_field}


# ---------- sanitize(供 AI 写报告时参照,本脚本 JSON 输出不直接用) ----------

def sanitize_cell(value):
    """净化动态字段,防破坏 Markdown 表格结构与注入。

    执行顺序:
      1. 转字符串;去换行 -> 空格。
      2. 转义 | < > & ;移除反引号 -> 单引号。
      3. 公式注入防护:以 = + - @ 开头 -> 前置单引号。
      4. 移除 Markdown 链接语法 []() ![]() 与 javascript: 协议。
    """
    if value is None:
        return ""
    s = str(value)
    s = s.replace("\r", " ").replace("\n", " ")
    # HTML 转义正确顺序: 先转 &(最优先),再转 < >。
    # 这样原始 & 变 &amp;,而 < 生成的 &lt; 里的 & 是新生成的,不会被二次转义。
    s = s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    s = s.replace("|", "\\|")
    s = s.replace("`", "'")
    s = s.replace("javascript:", "")
    # 链接语法
    import re
    s = re.sub(r"!\[([^\]]*)\]\([^)]*\)", r"\1", s)
    s = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", s)
    # 公式注入
    if s and s[0] in "=+-@":
        s = "'" + s
    return s


# ---------- 主入口 ----------

def main():
    if len(sys.argv) < 3:
        print(json.dumps(
            {"error": "用法: python analyze.py <profile|stats|freq> <文件路径>"},
            ensure_ascii=False))
        sys.exit(2)
    cmd, path = sys.argv[1], sys.argv[2]
    try:
        if cmd == "profile":
            result = cmd_profile(path)
        elif cmd == "stats":
            result = cmd_stats(path)
        elif cmd == "freq":
            result = cmd_freq(path)
        else:
            result = {"error": f"未知子命令: {cmd}(应为 profile/stats/freq)"}
    except FileNotFoundError:
        result = {"error": f"文件不存在: {path}"}
    except ValueError as e:
        result = {"error": str(e)}
    except Exception as e:  # 兜底:异常输入不崩溃,返回结构化错误
        result = {"error": f"分析失败: {type(e).__name__}: {e}"}
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
