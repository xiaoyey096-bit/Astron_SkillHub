#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
体检报告解读脚本（parse / compare 二合一）。

功能: 解析体检指标数据(指标名/数值/单位/参考范围),与内置参考范围比对,
     判定正常/轻度异常/明显异常并算偏离程度。供 AI 解读环节调用。
创建日期: 2026-08-03

输入: python health_check.py <子命令> <文件或文本>
  子命令:
    parse    <文件>   解析出每项指标(名/值/单位/参考范围)
    compare  <文件>   比对参考范围,判定分级

输出: 标准 JSON( stdout )。
     ① parse   -> items[{name,value,unit,ref}]
     ② compare -> items[{name,value,unit,ref,status,deviation_pct,direction,severity}]
"""

import sys
import os
import re
import json

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def read_input(arg):
    if os.path.exists(arg) and os.path.isfile(arg):
        with open(arg, "r", encoding="utf-8-sig") as f:
            return f.read()
    return arg


# ---------- 内置参考范围库(别名->规范名+范围) ----------

# 范围格式: (low, high, unit, is_lower_better)
# is_lower_better: True 表示该指标越低越好(如胆固醇), 超上限为异常;
#                  False 表示有下限(如HDL偏高有益)。
# 对于"阴性/阳性"类定性指标单独处理。
METRIC_DB = {
    "总胆固醇": {"aliases": ["tc", "chol", "总胆固醇"], "low": 0, "high": 5.2, "unit": "mmol/L", "direction": "high_bad", "meaning": "血液中总胆固醇水平，偏高与心血管风险相关"},
    "甘油三酯": {"aliases": ["tg", "甘油三酯"], "low": 0, "high": 1.7, "unit": "mmol/L", "direction": "high_bad", "meaning": "血液中甘油三酯，偏高与代谢、饮食相关"},
    "高密度脂蛋白": {"aliases": ["hdl-c", "hdl", "高密度脂蛋白"], "low": 1.04, "high": 99, "unit": "mmol/L", "direction": "low_bad", "meaning": "'好胆固醇'，偏高通常有益，偏低与心血管风险相关"},
    "低密度脂蛋白": {"aliases": ["ldl-c", "ldl", "低密度脂蛋白"], "low": 0, "high": 3.4, "unit": "mmol/L", "direction": "high_bad", "meaning": "'坏胆固醇'，偏高与心血管风险相关"},
    "空腹血糖": {"aliases": ["fbg", "glu", "空腹血糖", "血糖"], "low": 3.9, "high": 6.1, "unit": "mmol/L", "direction": "both", "meaning": "空腹血糖，反映糖代谢，偏高需排查糖尿病"},
    "谷丙转氨酶": {"aliases": ["alt", "谷丙", "谷丙转氨酶", "丙氨酸氨基转移酶"], "low": 0, "high": 40, "unit": "U/L", "direction": "high_bad", "meaning": "肝功能指标，偏高提示肝细胞损伤可能"},
    "谷草转氨酶": {"aliases": ["ast", "谷草", "谷草转氨酶", "天冬氨酸氨基转移酶"], "low": 0, "high": 40, "unit": "U/L", "direction": "high_bad", "meaning": "肝/心肌等指标，偏高提示损伤可能"},
    "尿素": {"aliases": ["bun", "尿素"], "low": 2.9, "high": 8.2, "unit": "mmol/L", "direction": "both", "meaning": "肾功能指标"},
    "肌酐": {"aliases": ["cr", "肌酐"], "low": 45, "high": 104, "unit": "μmol/L", "direction": "high_bad", "meaning": "肾功能指标，偏高提示肾功能可能异常"},
    "白细胞": {"aliases": ["wbc", "白细胞"], "low": 4, "high": 10, "unit": "×10^9/L", "direction": "both", "meaning": "免疫指标，偏高提示感染/炎症可能"},
    "血红蛋白": {"aliases": ["hgb", "hb", "血红蛋白"], "low": 130, "high": 175, "unit": "g/L", "direction": "both", "meaning": "贫血相关指标，偏低提示贫血可能"},
    "血小板": {"aliases": ["plt", "血小板"], "low": 125, "high": 350, "unit": "×10^9/L", "direction": "both", "meaning": "凝血相关指标"},
    "收缩压": {"aliases": ["收缩压", "高压"], "low": 90, "high": 139, "unit": "mmHg", "direction": "both", "meaning": "血压高压，≥140为高血压"},
    "舒张压": {"aliases": ["舒张压", "低压"], "low": 60, "high": 89, "unit": "mmHg", "direction": "both", "meaning": "血压低压，≥90为高血压"},
}

# 关键指标(异常必须建议就医)
KEY_METRICS = {"空腹血糖", "收缩压", "舒张压", "谷丙转氨酶", "谷草转氨酶", "肌酐"}


def _build_alias_index():
    """别名 -> 规范名。"""
    idx = {}
    for canon, info in METRIC_DB.items():
        for a in info["aliases"]:
            idx[a.lower()] = canon
        idx[canon.lower()] = canon
    return idx


ALIAS_INDEX = _build_alias_index()


# ---------- 子命令: parse ----------

def cmd_parse(text):
    """解析每项指标。"""
    items = []
    # 模式: 指标名 + 数值 + 单位 (+ 可选参考范围)
    # 参考范围模式: <X / X-Y / 男>X / 3.9-6.1 等
    lines = re.split(r"[\n；;]", text)
    for line in lines:
        line = line.strip()
        if not line:
            continue
        # 匹配: 指标名(中文或英文别名) + 可选英文别名/冒号 + 数值 + 单位
        # 指标名后可能跟着英文缩写(如 谷丙转氨酶 ALT 35), 中间允许字母/冒号/空格
        m = re.match(r"([一-龥A-Za-z]{2,12})\s*(?:[A-Za-z\-]+\s*)?[:：]?\s*([0-9.]+)\s*([一-龥A-Za-z/^0-9²μ×]+)?", line)
        if not m:
            continue
        raw_name = m.group(1).strip()
        # 去掉行首可能的序号/项目编号
        raw_name = re.sub(r"^[一二三四五六七八九十\d]+[、.．\)）]\s*", "", raw_name)
        try:
            val = float(m.group(2))
        except (ValueError, TypeError):
            continue
        unit = (m.group(3) or "").strip()
        # 规范名
        canon = ALIAS_INDEX.get(raw_name.lower())
        if not canon:
            # 尝试包含匹配
            for a, c in ALIAS_INDEX.items():
                if a in raw_name.lower() or raw_name.lower() in a:
                    canon = c
                    break
        if not canon:
            continue
        # 提取参考范围(若有)
        ref = None
        rm = re.search(r"参考值?\s*[:：]?\s*(<|≤|>|≥)?\s*([0-9.]+)(?:\s*[-~]\s*([0-9.]+))?", line)
        if rm:
            op = rm.group(1)
            lo = rm.group(2)
            hi = rm.group(3)
            ref = line[rm.start():rm.end()].replace("参考值", "").strip(" :：")
        items.append({
            "name": canon,
            "raw_name": raw_name,
            "value": val,
            "unit": unit or METRIC_DB[canon]["unit"],
            "ref_text": ref,
        })
    return {"items": items, "count": len(items)}


# ---------- 子命令: compare ----------

def cmd_compare(text):
    """比对参考范围,判定分级。"""
    parsed = cmd_parse(text)
    results = []
    for it in parsed["items"]:
        canon = it["name"]
        info = METRIC_DB.get(canon)
        if not info:
            continue
        val = it["value"]
        low, high = info["low"], info["high"]
        direction = info["direction"]

        status = "normal"
        severity = "green"
        deviation_pct = 0.0
        direction_str = ""

        if val < low:
            status = "low"
            direction_str = "偏低"
            deviation_pct = round(abs(low - val) / low * 100, 1)
            severity = _grade(deviation_pct, canon)
        elif val > high:
            status = "high"
            direction_str = "偏高"
            deviation_pct = round(abs(val - high) / high * 100, 1)
            # HDL 偏高有益,不报异常
            if direction == "low_bad" and canon == "高密度脂蛋白":
                status = "normal"
                severity = "green"
                direction_str = "偏高(通常有益)"
            else:
                severity = _grade(deviation_pct, canon)
        else:
            direction_str = "正常范围内"

        results.append({
            "name": canon,
            "value": val,
            "unit": it["unit"],
            "ref": f"{low}-{high}" if low > 0 else f"<{high}",
            "status": status,
            "direction": direction_str,
            "deviation_pct": deviation_pct,
            "severity": severity,
            "meaning": info["meaning"],
        })
    counts = {"green": 0, "yellow": 0, "red": 0}
    for r in results:
        counts[r["severity"]] = counts.get(r["severity"], 0) + 1
    return {"items": results, "counts": counts, "note": "分级为机器判定, AI 须结合指标特性复核, 异常项必须提示就医。"}


def _grade(deviation_pct, canon):
    """根据偏离程度和是否关键指标分级。"""
    if canon in KEY_METRICS and deviation_pct >= 10:
        return "red"
    if deviation_pct >= 20:
        return "red"
    if deviation_pct > 0:
        return "yellow"
    return "green"


# ---------- sanitize ----------

def sanitize_cell(value):
    if value is None:
        return ""
    s = str(value)
    s = s.replace("\r", " ").replace("\n", " ")
    s = s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    s = s.replace("|", "\\|").replace("`", "'")
    s = s.replace("javascript:", "")
    s = re.sub(r"!\[([^\]]*)\]\([^)]*\)", r"\1", s)
    s = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", s)
    if s and s[0] in "=+-@":
        s = "'" + s
    return s


def main():
    if len(sys.argv) < 3:
        print(json.dumps({"error": "用法: python health_check.py <parse|compare> <文件或文本>"}, ensure_ascii=False))
        sys.exit(2)
    cmd = sys.argv[1]
    try:
        text = read_input(sys.argv[2])
        if cmd == "parse":
            result = cmd_parse(text)
        elif cmd == "compare":
            result = cmd_compare(text)
        else:
            result = {"error": f"未知子命令: {cmd}(应为 parse/compare)"}
    except Exception as e:
        result = {"error": f"失败: {type(e).__name__}: {e}"}
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
