#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
会议纪要生成脚本（parse / extract 二合一）。

功能: 对会议文本做模式化抽取——发言人识别与切分、时间/日期识别、
     待办候选句子识别(关键词+责任人)。供 AI 在纪要生成环节调用,
     保证可复现;议题归类/决议判断等语义提炼由 AI 完成。
创建日期: 2026-08-03

输入: python notes_gen.py <子命令> <文件或文本>
  子命令:
    parse    <文件>   发言人识别与切分、统计
    extract  <文件>   待办候选、时间表达、发言人清单

输出: 标准 JSON( stdout )。
     ① parse   -> speakers[{name,count,sample}], total_turns
     ② extract -> action_candidates[{sentence,keyword,owner,due}],
                  time_expressions[], speakers[]
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


# ---------- 子命令: parse(发言人识别) ----------

# 发言人模式: 「中文姓名2-4字 + ：/ :」或「A/B/英文名 + :」
SPEAKER_PAT = re.compile(r"(?:^|\n)\s*([一-龥]{2,4}|[A-Z][a-z]*|[A-C])\s*[:：]\s*")


def cmd_parse(text):
    """识别发言人并切分。按「姓名：」标签分段。"""
    matches = list(SPEAKER_PAT.finditer(text))
    spans = []
    for i, m in enumerate(matches):
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        speaker = m.group(1).strip()
        content = text[start:end].strip()
        spans.append({"speaker": speaker, "content": content})

    from collections import Counter
    cnt = Counter(s["speaker"] for s in spans)
    speakers = []
    for name, c in cnt.most_common():
        sample = next((s["content"][:40] for s in spans if s["speaker"] == name), "")
        speakers.append({"name": name, "count": c, "sample": sample})
    return {
        "speakers": speakers,
        "total_turns": len(spans),
        "has_speaker_tags": len(spans) > 0,
    }


# ---------- 子命令: extract ----------

ACTION_KEYWORDS = [
    "负责", "牵头", "跟进", "推进", "落实", "执行", "去做", "来搞", "你来", "他去",
    "需要", "安排", "产出", "输出", "提交", "交付", "发送", "发一下",
    "确认", "核实", "查一下", "确认下", "对一下", "问一下",
    "修复", "修改", "调整", "优化", "改一下", "完善",
    "准备", "给到", "给出来", "敲定", "决定", "确定",
]

# 时间表达
TIME_PATTERNS = [
    r"\d{1,2}月\d{1,2}[日号]",
    r"\d{1,2}月\d{1,2}[日号][前后之前]",
    r"本周[一二三四五六天末]",
    r"下周[一二三四五六]",
    r"月底前",
    r"季度末",
    r"明天",
    r"后天",
    r"尽快",
    r"近期",
    r"ASAP",
    r"下次会议前",
    r"本周内",
    r"下周三前",
    r"\d+号之前",
]

# 人名(从 parse 结果 + 中文姓名启发)
def extract_owners(sentence, known_speakers):
    """从句子里找人名。优先已知发言人,其次中文姓名模式。"""
    owners = list(known_speakers)
    found = []
    for o in owners:
        if o in sentence:
            found.append(o)
    # 中文姓名 2-4 字(简单启发: 常见姓氏 + 名)
    if not found:
        m = re.findall(r"[赵钱孙李周吴郑王冯陈褚卫蒋沈韩杨朱秦尤许何吕施张孔曹严华金魏陶姜戚谢邹喻柏][一-龥]{1,3}", sentence)
        found = list(dict.fromkeys(m))[:2]
    return found


def cmd_extract(text):
    """提取待办候选、时间表达、发言人。"""
    # 先识别发言人
    parse_result = cmd_parse(text)
    known_speakers = [s["name"] for s in parse_result["speakers"]]

    # 按句切分(粗略: 按。！？换行)
    sentences = re.split(r"(?<=[。！？\n])", text)
    sentences = [s.strip() for s in sentences if s.strip() and len(s.strip()) > 4]

    action_candidates = []
    for sent in sentences:
        hit_kw = [k for k in ACTION_KEYWORDS if k in sent]
        if not hit_kw:
            continue
        owners = extract_owners(sent, known_speakers)
        # 截止
        dues = []
        for tp in TIME_PATTERNS:
            for m in re.finditer(tp, sent):
                dues.append(m.group(0))
        action_candidates.append({
            "sentence": sent[:80],
            "keyword": hit_kw[:3],
            "owner": owners[:2] if owners else [],
            "due": list(dict.fromkeys(dues))[:2],
        })

    # 全文时间表达
    time_expressions = []
    for tp in TIME_PATTERNS:
        for m in re.finditer(tp, text):
            time_expressions.append(m.group(0))

    return {
        "action_candidates": action_candidates,
        "time_expressions": list(dict.fromkeys(time_expressions)),
        "speakers": known_speakers,
        "note": "action_candidates 为机器命中, AI 需语义判断哪些是真正待办、补全责任人/截止。",
    }


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
        print(json.dumps({"error": "用法: python notes_gen.py <parse|extract> <文件或文本>"},
                         ensure_ascii=False))
        sys.exit(2)
    cmd = sys.argv[1]
    try:
        text = read_input(sys.argv[2])
        if cmd == "parse":
            result = cmd_parse(text)
        elif cmd == "extract":
            result = cmd_extract(text)
        else:
            result = {"error": f"未知子命令: {cmd}(应为 parse/extract)"}
    except Exception as e:
        result = {"error": f"失败: {type(e).__name__}: {e}"}
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
