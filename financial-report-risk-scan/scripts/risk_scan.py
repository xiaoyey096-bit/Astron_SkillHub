#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
金融材料风险扫描脚本（extract / risk 二合一）。

功能: 对金融材料文本做模式化抽取——关键财务数据(营收/净利润/现金流/负债率等)
     与风险信号识别(营收下滑/亏损/现金流为负/审计非标/诉讼担保等)。
     供 AI 在风险摘要环节调用,保证可复现;语义归纳由 AI 补。
创建日期: 2026-08-03

输入: python risk_scan.py <子命令> <文件或文本>
  子命令:
    extract  <文件>   抽取关键财务数据、识别材料类型
    risk     <文件>   扫描风险信号(按 references/risk-signals.md 规则)

输出: 标准 JSON( stdout )。
     ① extract -> doc_type, entity, period, financials[{metric,value,yoy,note}]
     ② risk    -> signals[{name,severity,evidence,hint}]
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


# ---------- 子命令: extract ----------

def cmd_extract(text):
    """抽取关键财务数据与材料类型。"""
    # 材料类型
    doc_type = "未知"
    if re.search(r"年报|年度报告", text):
        doc_type = "年报"
    elif re.search(r"招股说明书|招股书", text):
        doc_type = "招股说明书"
    elif re.search(r"审计报告", text):
        doc_type = "审计报告"
    elif re.search(r"财报|季度报告|半年报", text):
        doc_type = "财报"

    # 主体(粗略: 取"某某...公司"或首个公司名)
    entity = None
    m = re.search(r"([一-龥A-Za-z]{2,12}(?:股份|科技|集团|有限)?(?:公司|银行))", text)
    if m:
        entity = m.group(1)

    # 报告期
    period = None
    m = re.search(r"(20\d{2})\s*年", text)
    if m:
        period = m.group(1) + "年"

    financials = []

    # 数值捕获: 匹配 -?数字 + 可选单位(亿元/万元/元/百分比等), 不吃进"为/是"等字
    NUM = r"(-?\d+(?:\.\d+)?\s*(?:亿|万)?\s*元|%?)"

    def grab(metric_label, patterns):
        """按多个正则抓取某个指标,取首个命中。"""
        for pat in patterns:
            m = re.search(pat, text)
            if m:
                val = m.group(1).strip() if m.groups() else m.group(0).strip()
                # 找同比: 只在命中所在句内找(到下一个句号), 避免跨进下一条指标
                sent_end = text.find("。", m.end())
                sent_end = sent_end if sent_end != -1 else m.end() + 40
                window = text[m.end():min(sent_end, m.end() + 40)]
                yoy = None
                ym = re.search(r"同比(?:增长|下降|减少|增加|下滑)?\s*([-+]?\d+\.?\d*)\s*%", window)
                if ym:
                    direction = "下降" if any(w in window for w in ("下降", "减少", "下滑")) else "增长"
                    yoy = f"{direction}{ym.group(1)}%"
                financials.append({"metric": metric_label, "value": val[:40], "yoy": yoy, "note": ""})
                return

    grab("营业收入", [r"营业收入\s*(?:为|是|：|:)?\s*" + NUM, r"实现营业收入\s*" + NUM])
    grab("净利润", [r"净利润\s*(?:为|是|：|:)?\s*" + NUM])
    grab("经营性现金流净额", [r"经营活动[^。\n]*?现金流量?净额\s*(?:为|是|：|:)?\s*" + NUM])
    grab("资产负债率", [r"资产负债率\s*(?:为|是|：|:)?\s*(\d+\.?\d*\s*%)"])
    grab("应收账款", [r"应收账款[^。\n]*?余额?\s*(?:为|是|：|:)?\s*" + NUM])

    return {
        "doc_type": doc_type,
        "entity": entity,
        "period": period,
        "financials": financials,
    }


# ---------- 子命令: risk ----------

# 风险信号规则: (信号名, 正则, 等级, 提示)
RISK_RULES = [
    ("营收下滑", r"营业收入[^。]*同比[^。]*(?:下降|下滑|减少)\s*(\d+\.?\d*)\s*%",
     "high", "营收同比下滑，关注主业是否承压。"),
    ("净利润亏损", r"净利润[^。]*(?:亏损|为负|-\s*\d|-\d)",
     "high", "净利润为负或亏损，关注盈利能力与持续经营。"),
    ("亏损扩大", r"亏损[^。]*扩大|亏损[^。]*增加",
     "high", "亏损扩大，关注亏损趋势。"),
    ("经营性现金流为负", r"经营活动[^。]*现金流[^。]*(?:为负|负值|-\d)",
     "high", "经营性现金流为负，关注利润质量（是否有现金支撑）。"),
    ("资产负债率偏高", r"资产负债率[^，。；]*?为\s*(\d{2,3})\s*%",
     "mid", "资产负债率较高，关注偿债压力（≥70%需重点关注）。"),
    ("应收账款激增", r"应收账款[^。]*增长\s*(\d+\.?\d*)\s*%|应收账款[^。]*激增",
     "mid", "应收账款增长较快，关注回款风险与收入质量。"),
    ("审计非标意见", r"(?<!无)保留意见|无法表示意见|否定意见|带强调事项段",
     "high", "审计意见非标准无保留，高度重视。"),
    ("重大诉讼", r"诉讼|起诉|涉诉",
     "mid", "存在诉讼，关注潜在赔付与声誉影响。"),
    ("对外担保", r"对外担保[^。]*\d",
     "mid", "存在对外担保，关注或有负债风险。"),
    ("关联交易", r"关联交易[^。]*占(?:比|比)",
     "mid", "关联交易，关注公允性与利益输送风险。"),
    ("高管变动", r"(?:董事长|总经理|财务总监|董秘)[^。]*(?:辞职|离任|变动)",
     "low", "核心高管变动，关注经营稳定性。"),
    ("监管处罚", r"立案调查|监管处罚|警示函|行政处罚",
     "high", "被监管立案或处罚，关注合规风险。"),
    ("持续经营存疑", r"持续经营[^。]*(?:重大不确定性|存疑|能力存疑)",
     "high", "持续经营能力存疑，高度关注。"),
]


def cmd_risk(text):
    """扫描风险信号。"""
    signals = []
    for name, pat, sev, hint in RISK_RULES:
        for m in re.finditer(pat, text):
            # 否定语境排除: 命中前 8 字符内出现 "无/未/没有/不存在"(中间允许夹定语,
            # 如 "无重大诉讼""不存在对外担保""无监管处罚"), 视为不具备,跳过
            pre = text[max(0, m.start() - 8):m.start()]
            if re.search(r"(?:无|未|没有|不存在)[^，。；\n]{0,6}$", pre):
                continue
            # 取命中所在句作为依据
            start = max(0, text.rfind("。", 0, m.start()) + 1, m.start() - 30)
            end = text.find("。", m.end())
            end = end if end != -1 else min(len(text), m.end() + 30)
            evidence = text[start:end].strip()
            # 提取关键数字(若有)
            num = m.group(1) if m.groups() else None
            signals.append({
                "name": name,
                "severity": sev,
                "evidence": evidence[:80],
                "value": num,
                "hint": hint,
            })
    # 资产负债率特殊: 只在 >=70 时报 high, 否则按数值报 mid 或不报
    # (上面规则已抓所有资产负债率数字, 这里二次判断)
    cleaned = []
    for s in signals:
        if s["name"] == "资产负债率偏高" and s.get("value"):
            try:
                v = int(re.search(r"(\d+)", s["value"]).group(1))
                if v >= 70:
                    s["severity"] = "high"
                elif v < 50:
                    continue  # 低负债不报
            except Exception:
                pass
        cleaned.append(s)
    # 去重(同名信号取一条)
    seen = set()
    deduped = []
    for s in cleaned:
        if s["name"] in seen:
            continue
        seen.add(s["name"])
        deduped.append(s)
    # 按等级排序
    order = {"high": 0, "mid": 1, "low": 2}
    deduped.sort(key=lambda x: order.get(x["severity"], 9))
    return {"signals": deduped, "count": len(deduped)}


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
        print(json.dumps({"error": "用法: python risk_scan.py <extract|risk> <文件或文本>"}, ensure_ascii=False))
        sys.exit(2)
    cmd = sys.argv[1]
    try:
        text = read_input(sys.argv[2])
        if cmd == "extract":
            result = cmd_extract(text)
        elif cmd == "risk":
            result = cmd_risk(text)
        else:
            result = {"error": f"未知子命令: {cmd}(应为 extract/risk)"}
    except Exception as e:
        result = {"error": f"失败: {type(e).__name__}: {e}"}
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
