#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
情绪日记分析脚本（crisis / classify / stressor / cognition 四合一）。

功能: 对用户输入的情绪/压力文本做确定性分析——危机信号筛查(一票否决)、
     情绪归类与强度评估、压力源维度归因、不合理思维模式识别。
     供 AI 在情绪日记回应环节调用,保证可复现;语义修正由 AI 补。
创建日期: 2026-08-03

输入: 命令行参数 <子命令> <文本或文件路径>
  子命令:
    crisis     <文本/文件>  危机信号筛查(自伤/自杀/伤人),命中即 flag=True
    classify   <文本/文件>  情绪归类(类型+强度,基于情绪词库)
    stressor   <文本/文件>  压力源维度归因(工作/人际/经济/健康/未来/丧失)
    cognition  <文本/文件>  不合理思维模式识别(绝对化/灾难化/以偏概全/贴标签/读心术)

输出: 标准 JSON( stdout )。字段含义见各函数注释。
     ① crisis    -> flag(bool), hits[{keyword,type,line}]
     ② classify  -> emotions[{type,strength,hits[]}], dominant
     ③ stressor  -> dimensions[{dim,hits[]}]
     ④ cognition -> distortions[{type,hits[],example}]
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
REF = os.path.join(HERE, "..", "references")


# ---------- 读取输入(文本或文件) ----------

def read_input(arg):
    """若 arg 是已存在文件路径则读文件,否则当作文本。"""
    if os.path.exists(arg) and os.path.isfile(arg):
        with open(arg, "r", encoding="utf-8-sig") as f:
            return f.read()
    return arg


# ---------- 否定词处理 ----------

NEG_WORDS = ("不", "没", "无", "非", "别", "未", "毫不")


def has_negation_before(text, pos, window=4):
    """检查 pos 位置前 window 个字符内是否有否定词。"""
    seg = text[max(0, pos - window):pos]
    return any(n in seg for n in NEG_WORDS)


# ---------- 子命令: crisis ----------

# 危机信号词(自伤/自杀/伤人意图)。命中任一即 flag=True。
CRISIS_PATTERNS = [
    (r"不想活", "自杀意图"),
    (r"活不下去", "自杀意图"),
    (r"活着没意思", "自杀意图"),
    (r"活着.{0,4}没.{0,2}意义", "自杀意图"),
    (r"想死", "自杀意图"),
    (r"不想活了", "自杀意图"),
    (r"结束自己", "自杀意图"),
    (r"结束这一切", "自杀意图"),
    (r"了结自己", "自杀意图"),
    (r"如果我(不在|死了|没了)", "自杀意图"),
    (r"自杀", "自杀意图"),
    (r"自残", "自伤"),
    (r"割(腕|手)", "自伤"),
    (r"想伤害自己", "自伤"),
    (r"伤害别人", "伤人"),
    (r"同归于尽", "伤人"),
    (r"一起死", "伤人/自杀"),
    (r"活得太累", "高风险表达"),
    (r"撑不下去", "高风险表达"),
    (r"没有我.{0,4}都.{0,2}轻松", "自杀意图"),
]


def cmd_crisis(text):
    """危机信号筛查。命中即 flag=True,返回所有命中。"""
    hits = []
    for pat, typ in CRISIS_PATTERNS:
        for m in re.finditer(pat, text):
            # 排除明显否定语境(如"我不想死")——但危机词多为肯定意图,谨慎处理
            if has_negation_before(text, m.start(), window=3):
                # "不想死" 这类否定反而可能是保护因素,但仍记录供 AI 复核
                hits.append({"keyword": m.group(0), "type": typ + "(前有否定,需AI复核)", "pos": m.start()})
            else:
                hits.append({"keyword": m.group(0), "type": typ, "pos": m.start()})
    return {"flag": len(hits) > 0, "hits": hits}


# ---------- 子命令: classify ----------

def load_emotion_lexicon():
    """解析 emotion-lexicon.md 为 [(词, 类型, 强度)]。失败用内置兜底。"""
    entries = []
    fallback = [
        ("焦虑", "anxiety", 2), ("紧张", "anxiety", 2), ("心慌", "anxiety", 2),
        ("担心", "anxiety", 1), ("害怕", "anxiety", 2), ("恐慌", "anxiety", 3),
        ("不安", "anxiety", 2), ("喘不过气", "anxiety", 3),
        ("难过", "depression", 2), ("低落", "depression", 2), ("郁闷", "depression", 2),
        ("失落", "depression", 2), ("无力", "depression", 2), ("绝望", "depression", 3),
        ("想哭", "depression", 2), ("没意思", "depression", 2), ("疲惫", "depression", 2),
        ("累", "depression", 1), ("崩溃", "depression", 3), ("撑不住", "depression", 3),
        ("撑不下去", "depression", 3), ("心力交瘁", "depression", 3),
        ("生气", "anger", 2), ("愤怒", "anger", 3), ("烦躁", "anger", 2),
        ("烦", "anger", 1), ("憋屈", "anger", 2), ("抓狂", "anger", 3),
        ("平静", "calm", 1), ("舒服", "calm", 1), ("开心", "calm", 1),
        ("满足", "calm", 1), ("轻松", "calm", 1), ("踏实", "calm", 1), ("挺好", "calm", 1),
        ("迷茫", "confusion", 2), ("孤独", "lonely", 2), ("无助", "lonely", 2),
    ]
    path = os.path.join(REF, "emotion-lexicon.md")
    try:
        with open(path, "r", encoding="utf-8") as f:
            cur_type = None
            for line in f:
                line = line.strip()
                if line.startswith("##") and "类" in line:
                    if "焦虑" in line: cur_type = "anxiety"
                    elif "低落" in line: cur_type = "depression"
                    elif "愤怒" in line: cur_type = "anger"
                    elif "平静" in line or "正向" in line: cur_type = "calm"
                    elif "迷茫" in line: cur_type = "confusion"
                    elif "孤独" in line: cur_type = "lonely"
                m = re.match(r"\|\s*([^|]+?)\s*\|\s*(\d)\s*\|", line)
                if m and cur_type:
                    word = m.group(1).strip()
                    if word and word != "词":
                        entries.append((word, cur_type, int(m.group(2))))
    except Exception:
        return fallback
    return entries if entries else fallback


INTENSIFIER = ("非常", "特别", "极其", "十分", "太", "超级", "快疯", "要疯")


def cmd_classify(text):
    """情绪归类与强度评估。"""
    lex = load_emotion_lexicon()
    by_type = {}
    for word, typ, strength in lex:
        for m in re.finditer(re.escape(word), text):
            if has_negation_before(text, m.start(), window=3):
                continue
            s = strength
            # 程度副词 +1
            pre = text[max(0, m.start() - 3):m.start()]
            if any(adv in pre for adv in INTENSIFIER):
                s = min(3, s + 1)
            by_type.setdefault(typ, []).append({"word": word, "strength": s})
    emotions = []
    for typ, hits in by_type.items():
        max_s = max(h["strength"] for h in hits)
        emotions.append({"type": typ, "strength": max_s, "hits": [h["word"] for h in hits]})
    emotions.sort(key=lambda x: (-x["strength"], -len(x["hits"])))
    dominant = emotions[0]["type"] if emotions else None
    return {"emotions": emotions, "dominant": dominant}


# ---------- 子命令: stressor ----------

STRESSOR_DIMS = {
    "work_study": ["deadline", "截止", "交付", "交差", "汇报", "kpi", "考核", "绩效",
                   "加班", "项目", "任务", "老板", "领导", "上级", "客户", "同事", "开会",
                   "报告", "论文", "考试", "复习", "作业", "答辩", "导师", "考研", "挂科",
                   "成绩", "卷", "内卷", "996", "被批", "挨骂", "加需求", "做不完"],
    "relationship": ["家人", "爸妈", "父母", "伴侣", "对象", "男朋友", "女朋友", "老公",
                     "老婆", "分手", "吵架", "冲突", "冷战", "朋友", "闺蜜", "同事关系",
                     "被孤立", "被误解", "不被理解", "婆媳", "育儿", "孩子", "带娃",
                     "朋友也不理", "不理我"],
    "finance": ["没钱", "穷", "工资", "房贷", "车贷", "房租", "欠款", "债务", "花销",
                "失业", "找工作", "面试被拒", "经济", "账单", "降薪", "年终"],
    "health": ["生病", "不舒服", "疼", "痛", "失眠", "睡不着", "熬夜", "疲劳", "体检",
               "医院", "看病", "吃药", "肠胃", "头疼", "颈椎"],
    "future_self": ["未来", "前途", "迷茫", "没方向", "没目标", "自我怀疑", "不自信",
                    "自卑", "比不上", "同龄人", "别人都", "落后", "一事无成", "没用",
                    "废物", "没出息", "什么都做不好"],
    "loss": ["分手", "离职", "辞职", "失去", "走", "离开", "去世", "离世", "离别",
             "结束", "失败", "被拒", "落榜", "错过", "遗憾"],
}


def cmd_stressor(text):
    """压力源维度归因。"""
    dims = []
    for dim, words in STRESSOR_DIMS.items():
        hits = []
        for w in words:
            for m in re.finditer(re.escape(w), text):
                hits.append(w)
        if hits:
            # 去重统计
            from collections import Counter
            cnt = Counter(hits)
            dims.append({"dim": dim, "hits": list(cnt), "count": sum(cnt.values())})
    dims.sort(key=lambda x: -x["count"])
    return {"dimensions": dims}


# ---------- 子命令: cognition ----------

COGNITION_PATTERNS = {
    "all_or_nothing": [r"必须", r"一定要", r"应该", r"不应该", r"总是", r"从来不",
                       r"永远", r"每次都", r"所有人", r"没人", r"绝不"],
    "catastrophizing": [r"完了", r"全完了", r"毁了", r"没救了", r"糟透了", r"彻底",
                        r"完蛋", r"死定了", r"没希望了", r"白干了", r"搞砸了"],
    "overgeneralization": [r"又一次", r"总是这样", r"每次", r"我就知道", r"果然",
                           r"老是", r"又.{0,3}失败"],
    "labeling": [r"我是.{0,4}(废物|失败|没用|蠢|垃圾|差劲)", r"我真(笨|蠢|没用|差劲)",
                 r"我就知道我不行", r"什么都做不好", r"一事无成"],
    "mind_reading": [r"肯定觉得", r"一定认为", r"他们肯定", r"他肯定是", r"肯定在",
                     r"应该觉得", r"想必", r"不理我"],
}


def cmd_cognition(text):
    """不合理思维模式识别。"""
    found = []
    for typ, pats in COGNITION_PATTERNS.items():
        hits = []
        for pat in pats:
            for m in re.finditer(pat, text):
                # 取命中所在的整句(粗略: 前后到标点)
                start = max(0, text.rfind("。", 0, m.start()) + 1, m.start() - 20)
                end = text.find("。", m.end())
                end = end if end != -1 else min(len(text), m.end() + 20)
                example = text[start:end].strip()
                hits.append(example)
        if hits:
            found.append({"type": typ, "hits_examples": list(dict.fromkeys(hits))[:3]})
    return {"distortions": found}


# ---------- sanitize(供 AI 写报告参照) ----------

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


# ---------- 主入口 ----------

def main():
    if len(sys.argv) < 3:
        print(json.dumps({"error": "用法: python mood_analyze.py <crisis|classify|stressor|cognition> <文本或文件>"},
                         ensure_ascii=False))
        sys.exit(2)
    cmd = sys.argv[1]
    try:
        text = read_input(sys.argv[2])
        if cmd == "crisis":
            result = cmd_crisis(text)
        elif cmd == "classify":
            result = cmd_classify(text)
        elif cmd == "stressor":
            result = cmd_stressor(text)
        elif cmd == "cognition":
            result = cmd_cognition(text)
        else:
            result = {"error": f"未知子命令: {cmd}(应为 crisis/classify/stressor/cognition)"}
    except Exception as e:
        result = {"error": f"分析失败: {type(e).__name__}: {e}"}
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
