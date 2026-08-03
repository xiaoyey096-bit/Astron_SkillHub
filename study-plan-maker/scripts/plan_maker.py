#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
学习计划生成脚本（breakdown / schedule 二合一）。

功能: 拆解学习目标为能力树、按可用时间做三阶段(基础/进阶/实战)分配。
     供 AI 在计划生成环节调用,保证时间分配可复现;个性化编排由 AI 补。
创建日期: 2026-08-03

输入: python plan_maker.py <子命令> <参数>
  子命令:
    breakdown <目标关键词>   返回该目标的能力树(内置库,未覆盖返回generic模板)
    schedule  <总周数> <每周小时>  返回三阶段周数/小时分配+每周任务量上限

输出: 标准 JSON( stdout )。
     ① breakdown -> target, modules[{name,difficulty,stage,resource}]
     ② schedule  -> total_weeks, weekly_hours, stages{basic/advanced/practice:{weeks,hours,tasks_per_week}}, buffer_pct
"""

import sys
import os
import re
import json

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
TREES = os.path.join(HERE, "..", "references", "skill-trees.md")


# ---------- 内置能力树(兜底,优先读 skill-trees.md) ----------

BUILTIN_TREES = {
    "python数据分析": {
        "target": "Python数据分析",
        "modules": [
            {"name": "Python基础(语法/数据类型/函数/文件IO)", "difficulty": 1, "stage": "basic", "resource": "入门视频+交互练习"},
            {"name": "NumPy(数组/向量化)", "difficulty": 2, "stage": "basic", "resource": "官方教程+练习题"},
            {"name": "Pandas(DataFrame/清洗/聚合)", "difficulty": 2, "stage": "advanced", "resource": "视频+实战数据集"},
            {"name": "数据可视化(Matplotlib/Seaborn)", "difficulty": 2, "stage": "advanced", "resource": "教程+模仿案例"},
            {"name": "统计基础(描述统计/分布/检验)", "difficulty": 2, "stage": "advanced", "resource": "视频+习题"},
            {"name": "实战项目(完整分析流程)", "difficulty": 3, "stage": "practice", "resource": "真实数据集做项目"},
        ],
    },
    "考研英语": {
        "target": "考研英语",
        "modules": [
            {"name": "词汇(5500核心词)", "difficulty": 2, "stage": "basic", "resource": "词书+APP每日背"},
            {"name": "长难句/语法", "difficulty": 2, "stage": "basic", "resource": "视频+每日一句"},
            {"name": "阅读理解", "difficulty": 3, "stage": "advanced", "resource": "历年真题精读"},
            {"name": "翻译", "difficulty": 3, "stage": "advanced", "resource": "真题+对照练习"},
            {"name": "写作(大小作文)", "difficulty": 2, "stage": "advanced", "resource": "模板+仿写"},
            {"name": "真题模拟冲刺", "difficulty": 3, "stage": "practice", "resource": "历年真题+模考"},
        ],
    },
}


def load_trees():
    """解析 skill-trees.md 为 {关键词: tree}。失败用内置。"""
    trees = {}
    try:
        with open(TREES, "r", encoding="utf-8") as f:
            content = f.read()
        # 按 ## 标题分块
        blocks = re.split(r"^## ", content, flags=re.M)
        for blk in blocks[1:]:
            lines = blk.strip().splitlines()
            if not lines:
                continue
            header = lines[0].strip()
            # 提取关键词(括号里的英文或标题)
            kw = header.split("（")[0].split("(")[0].strip()
            modules = []
            for line in lines:
                m = re.match(r"\|\s*([^|]+?)\s*\|\s*(\d)\s*\|\s*([^|]+?)\s*\|", line)
                if m:
                    name = m.group(1).strip()
                    if name in ("模块", "------"):
                        continue
                    diff = int(m.group(2))
                    res = m.group(3).strip()
                    # 难度映射阶段: 1->basic, 2->advanced, 3->practice(粗略, AI可调)
                    stage = "basic" if diff <= 1 else ("advanced" if diff == 2 else "practice")
                    modules.append({"name": name, "difficulty": diff, "stage": stage, "resource": res})
            if modules:
                trees[kw.lower()] = {"target": kw, "modules": modules}
    except Exception:
        pass
    # 合并内置(内置优先级低,文件没读到时兜底)
    for k, v in BUILTIN_TREES.items():
        trees.setdefault(k.lower(), v)
    return trees


def cmd_breakdown(keyword):
    """按关键词返回能力树。未覆盖返回 generic 模板。"""
    trees = load_trees()
    kw = keyword.strip().lower()
    # 模糊匹配: 关键词包含或被包含
    matched = None
    for k, v in trees.items():
        if k == kw or k in kw or kw in k:
            matched = v
            break
    if matched:
        return {**matched, "matched": True}
    # 未覆盖: 返回通用模板,提示 AI 现场拆解
    return {
        "target": keyword,
        "modules": [
            {"name": "基础概念/入门", "difficulty": 1, "stage": "basic", "resource": "入门视频+教材"},
            {"name": "核心技能/工具", "difficulty": 2, "stage": "advanced", "resource": "教程+练习"},
            {"name": "进阶/综合应用", "difficulty": 2, "stage": "advanced", "resource": "案例+专项"},
            {"name": "实战/项目/真题", "difficulty": 3, "stage": "practice", "resource": "完整项目/真题"},
        ],
        "matched": False,
        "note": "目标不在内置能力树库,已返回通用模板,请 AI 结合目标现场细化拆解。",
    }


# ---------- schedule ----------

def cmd_schedule(total_weeks, weekly_hours):
    """三阶段时间分配。

    基础40%/进阶35%/实战25%, 零基础可由 AI 调整(本函数给默认)。
    每周任务量上限 = weekly_hours / 1.2 (按1.2小时/任务)。
    保留10%缓冲。
    """
    try:
        tw = int(total_weeks)
        wh = float(weekly_hours)
    except (ValueError, TypeError):
        return {"error": "总周数和每周小时需为数字"}
    if tw <= 0 or wh <= 0:
        return {"error": "总周数和每周小时需为正数"}

    # 阶段周数(四舍五入,保证总和=tw)
    basic_w = max(1, round(tw * 0.40))
    practice_w = max(1, round(tw * 0.25))
    advanced_w = max(1, tw - basic_w - practice_w)
    # 修正总和
    while basic_w + advanced_w + practice_w > tw:
        if advanced_w > 1:
            advanced_w -= 1
        elif basic_w > 1:
            basic_w -= 1
        else:
            practice_w -= 1
    while basic_w + advanced_w + practice_w < tw:
        advanced_w += 1

    # 每周有效小时(留10%缓冲)
    effective_weekly = wh * 0.9
    tasks_per_week = max(1, round(effective_weekly / 1.2))

    return {
        "total_weeks": tw,
        "weekly_hours": wh,
        "effective_weekly_hours": round(effective_weekly, 1),
        "buffer_pct": 10,
        "stages": {
            "basic": {"weeks": basic_w, "hours": round(basic_w * effective_weekly, 1)},
            "advanced": {"weeks": advanced_w, "hours": round(advanced_w * effective_weekly, 1)},
            "practice": {"weeks": practice_w, "hours": round(practice_w * effective_weekly, 1)},
        },
        "tasks_per_week_max": tasks_per_week,
        "note": "阶段占比默认 基础40%/进阶35%/实战25%, 零基础建议AI把基础阶段加长。",
    }


# ---------- sanitize ----------

def sanitize_cell(value):
    """净化动态字段(同其他 Skill 规则)。"""
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
        print(json.dumps({"error": "用法: python plan_maker.py <breakdown 关键词 | schedule 总周数 每周小时>"},
                         ensure_ascii=False))
        sys.exit(2)
    cmd = sys.argv[1]
    try:
        if cmd == "breakdown":
            result = cmd_breakdown(sys.argv[2])
        elif cmd == "schedule":
            if len(sys.argv) < 4:
                result = {"error": "schedule 需要: 总周数 每周小时"}
            else:
                result = cmd_schedule(sys.argv[2], sys.argv[3])
        else:
            result = {"error": f"未知子命令: {cmd}(应为 breakdown/schedule)"}
    except Exception as e:
        result = {"error": f"失败: {type(e).__name__}: {e}"}
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
