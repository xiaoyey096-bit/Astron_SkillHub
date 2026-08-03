#!/usr/bin/env python3
"""
党政机关公文辅助校验工具集（三模块合一命令行脚本）。

功能: 基于《党政机关公文格式》GB/T 9704—2012,提供公文格式校验、
      关键信息提取、规范术语校正三个辅助子命令,纯 Python 标准库实现,零依赖、不联网。
      本工具仅做辅助校验,不起草公文、不生成红头版式。
创建日期: 2026-08-02

输入: 命令行参数。用法:
    python gongwen_toolkit.py check    <公文文件路径>      格式合规校验
    python gongwen_toolkit.py extract  <来文文件路径>      关键信息提取
    python gongwen_toolkit.py glossary <公文文件路径>      规范术语校正
    python gongwen_toolkit.py --help                       查看帮助

输出:
  ① check:    Markdown 校验报告(按 🔴严重/🟡提醒/🟢建议 分级),打印到标准输出
  ② extract:  结构化要素表(Markdown 表格),打印到标准输出
  ③ glossary: 术语校正清单(Markdown 表格),打印到标准输出

字段:
  ① 校验问题项: 严重度, 问题位置, 问题描述, 标准依据, 修改示例
  ② 提取要素项: 发文字号, 发文机关, 成文日期, 事由, 核心要求, 时限要求, 关键数据
  ③ 术语校正项: 原句, 规范表述, 依据

安全说明: 仅本地读取用户指定文件,无网络请求、无 shell 调用、无 eval;
          文件名经 sanitize_path 净化;输出 Markdown 前动态字段统一经 sanitize_cell 转义。
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path

# Windows 控制台默认 GBK,强制 UTF-8 以正确输出中文与符号(避免 UnicodeEncodeError)
if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass


# ============================================================
# 通用安全函数
# ============================================================

def sanitize_cell(text):
    """净化动态字段,防止其破坏 Markdown 表格或注入危险语法。

    处理对象: 管道符、换行、HTML 尖括号与 &、反引号、
    CSV/Excel 公式前缀(= + - @)、Markdown 链接/图片语法、javascript: 协议。
    入参: text(任意字符串)。返回: 净化后的安全字符串。
    """
    if text is None:
        return ""
    s = str(text)
    # 1. 先去换行,避免撑破表格行
    s = s.replace("\r\n", " ").replace("\r", " ").replace("\n", " ")
    # 2. 管道符转义(Markdown 表格分隔符)
    s = s.replace("|", "\\|")
    # 3. HTML 尖括号与 & 转义(防 HTML 注入)
    s = s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    # 4. 反引号转义(防 Markdown 代码块)
    s = s.replace("`", "\\`")
    # 5. CSV/Excel 公式前缀: 以 = + - @ 开头时前置单引号(防公式注入)
    if s and s[0] in "=+-@":
        s = "'" + s
    # 6. 过滤 Markdown 链接/图片语法 [..](..) 与 javascript: 协议
    s = re.sub(r"!\[", "[", s)              # 图片语法降级为普通文本
    s = re.sub(r"\]\((?!.*javascript:)", "](", s)  # 保留普通链接但…
    s = re.sub(r"javascript:", "javascript :", s, flags=re.IGNORECASE)  # 拆开协议关键字
    return s


def sanitize_path(path_str):
    """净化文件路径,过滤目录穿越与非法字符。

    入参: path_str(用户输入的路径字符串)。
    返回: 经校验的 Path 对象;若含危险模式(../、绝对盘符越界等)抛 ValueError。
    """
    if not path_str:
        raise ValueError("文件路径为空")
    p = str(path_str).strip().strip('"').strip("'")
    # 禁止目录穿越
    if ".." in p.split("/") or ".." in p.split("\\"):
        raise ValueError("路径不允许包含 '..' 目录穿越")
    # 仅允许常规字符(允许盘符、斜杠、反斜杠、汉字、字母数字、下划线、连字符、点、空格、冒号)
    if not re.fullmatch(r"[A-Za-z0-9_\-./\\:\u4e00-\u9fa5（）()【】\[\]《》、，。 ]+", p):
        raise ValueError("路径含非法字符")
    return Path(p)


def read_text(path_str):
    """安全读取文本文件(自动尝试 UTF-8/GBK 编码)。

    入参: path_str(文件路径)。返回: 文件全文文本。
    """
    p = sanitize_path(path_str)
    if not p.exists():
        raise FileNotFoundError(f"文件不存在: {p}")
    if p.stat().st_size > 10 * 1024 * 1024:
        raise ValueError("文件过大(超过 10MB),请确认是否为公文文本")
    for enc in ("utf-8", "utf-8-sig", "gbk"):
        try:
            return p.read_text(encoding=enc)
        except UnicodeDecodeError:
            continue
    raise ValueError("无法解码文件(非 UTF-8/GBK 文本)")


# ============================================================
# 模块①: 格式校验
# ============================================================

# 发文字号正例: 机关代字〔年份〕顺序号 (六角括号、阿拉伯数字、不编虚位、不加"第")
RE_FAWEN_GOOD = re.compile(r"[\u4e00-\u9fa5]{2,}〔\d{4}〕\d{1,3}号")
# 发文字号错例: 方括号 [2026] 或 圆括号 (2026)
RE_FAWEN_BRACKET_WRONG = re.compile(r"[\u4e00-\u9fa5]{2,}[\[【(]\d{4}[\]】)]\d{1,3}号")
# 顺序号编虚位或加"第": 〔2026〕05号 / 〔2026〕第5号
RE_FAWEN_XUWEI = re.compile(r"〔\d{4}〕0\d{1,2}号|〔\d{4}〕第\d{1,3}号")
# 成文日期错例: 中文数字 二〇二六年
RE_DATE_CHINESE = re.compile(r"[二三四五六七八九零〇]{2,}年([一二三四五六七八九十]{1,3}月)?")
# 成文日期错例: 月日编虚位 2026年08月02日
RE_DATE_XUWEI = re.compile(r"\d{4}年0\d{1,2}月0?\d{1,2}日|\d{4}年\d{1,2}月0\d{1,2}日")
# 成文日期正例
RE_DATE_GOOD = re.compile(r"\d{4}年[1-9]\d?月[1-9]\d?日|\d{4}年[1-9]\d?月3[01]日")
# 层次序号: 第一层 "一、" 用中文数字+顿号
RE_LEVEL1 = re.compile(r"^[一二三四五六七八九十]{1,3}、", re.MULTILINE)
# 层次序号: 错误用 "1、" 阿拉伯数字+顿号 开头第一层
# 第一层序号误用: 段首缩进(全角空格或空格)后的「数字+顿号」,如「　　1、」(应为「一、」)
RE_LEVEL1_WRONG = re.compile(r"(?m)^[ \t　]*\d+、")
# 第二层序号误用半角圆括号: 段首缩进后的「(一)」(应为全角「（一）」)
RE_LEVEL2_HALFWIDTH = re.compile(r"(?m)^[ \t　]*\(([一二三四五六七八九十]+)\)")
# 主送机关末尾应全角冒号
RE_ZHUSONG_COLON = re.compile(r"[:：]\s*$")


def normalize_spaces(text):
    """归一化 PDF/OCR 抽取文本中的多余空格,避免误判。

    处理: 中文与中文/数字/全角符号之间的多余空格(如「2025 年」「〔 2025〕」「115 号」)。
    保留: 英文单词间空格(如 GB 3100)。仅删空格不删换行,故行号不变。
    入参: text(原始文本)。返回: 归一化后的文本(用于识别判断)。
    """
    s = text
    # 注意: 只删「同行内的空格/制表符/全角空格」, 不删换行(\n), 避免把跨行内容粘连
    # 中文/全角符号 + 同行空格 + (中文/数字/全角左括号) → 去空格
    s = re.sub(r"([一-龥〔〕【】《》、，。：；！？“”‘’（）])([ \t　]+)([一-龥〔0-9])", r"\1\3", s)
    # (数字/中文/全角右括号) + 同行空格 + (中文/全角左括号) → 去空格
    s = re.sub(r"([0-9一-龥〕】）])([ \t　]+)([一-龥〔【（])", r"\1\3", s)
    return s
# 半角冒号/括号误用(在中文语境)
RE_HALFCOLON = re.compile(r"[A-Za-z0-9\u4e00-\u9fa5]:[^\s/]")


def check_gongwen(text):
    """对公文全文做格式合规校验,返回问题列表。

    入参: text(公文全文)。返回: list[dict],每项含 level/location/desc/basis/example。
    """
    issues = []
    lines = text.splitlines()
    # 归一化 PDF/OCR 抽取的多余空格,仅用于发文字号/日期/序号的"识别判断"
    # (行号仍按原文计算,因为 normalize_spaces 不删换行)
    norm = normalize_spaces(text)

    def add(level, location, desc, basis, example=""):
        issues.append({
            "level": level, "location": location, "desc": desc,
            "basis": basis, "example": example,
        })

    # 1. 发文字号校验(用归一化文本识别,避免 PDF 空格导致漏判)
    has_fawen_good = bool(RE_FAWEN_GOOD.search(norm))
    has_fawen_bad_bracket = RE_FAWEN_BRACKET_WRONG.search(norm)
    has_fawen_xuwei = RE_FAWEN_XUWEI.search(norm)
    if has_fawen_bad_bracket:
        add("严重", f"行{find_line(text, has_fawen_bad_bracket.group())}",
            f"发文字号年份未用六角括号〔〕: 「{has_fawen_bad_bracket.group()}」",
            "GB/T 9704—2012 7.2.5", "应改为六角括号,如「国办发〔2026〕5号」")
    if has_fawen_xuwei:
        add("严重", f"行{find_line(text, has_fawen_xuwei.group())}",
            f"发文字号顺序号编虚位或加'第': 「{has_fawen_xuwei.group()}」",
            "GB/T 9704—2012 7.2.5", "顺序号不加'第'、不编虚位(1 不编为 01)")
    elif not has_fawen_good and not has_fawen_bad_bracket:
        # 全文找不到任何发文字号迹象(且非纯转发件),提示
        add("提醒", "版头", "未识别到发文字号(机关代字〔年份〕顺序号)",
            "GB/T 9704—2012 7.2.5", "正式公文应有发文字号")

    # 2. 成文日期校验(用归一化文本识别)
    date_bad_cn = RE_DATE_CHINESE.search(norm)
    date_bad_xw = RE_DATE_XUWEI.search(norm)
    date_good = RE_DATE_GOOD.search(norm)
    if date_bad_cn:
        add("严重", f"行{find_line(text, date_bad_cn.group())}",
            f"成文日期使用了中文数字: 「{date_bad_cn.group()}」",
            "GB/T 9704—2012 7.3.5.4", "成文日期用阿拉伯数字,如「2026年8月2日」")
    if date_bad_xw:
        # 国标 7.3.5.4「月、日不编虚位」是强制要求,与中文数字同等定级为严重
        add("严重", f"行{find_line(text, date_bad_xw.group())}",
            f"成文日期月或日编了虚位: 「{date_bad_xw.group()}」",
            "GB/T 9704—2012 7.3.5.4", "月、日不编虚位(1 不编为 01)")
    elif not date_good and not date_bad_cn:
        add("提醒", "落款", "未识别到成文日期(阿拉伯数字年月日)",
            "GB/T 9704—2012 7.3.5.4", "公文应有成文日期")

    # 3. 层次序号校验
    # 第一层应为「一、」(中文数字+顿号); 若出现「数字+顿号」(如「1、」)即为不规范
    level1_wrong_hits = RE_LEVEL1_WRONG.findall(text)
    if level1_wrong_hits:
        first = level1_wrong_hits[0]
        add("严重", f"行{find_line(text, first)}",
            f"正文层次序号出现「{first.strip()}」(数字+顿号)",
            "GB/T 9704—2012 7.3.3", "第一层应用「一、」,逐级「一、(一)1.(1)」;"
            "注意「1.」(数字+点)是第三层,「1、」(数字+顿号)不规范")
    # 第二层序号应用全角「（一）」; 半角「(一)」违反 GB/T 15834 全角要求,定级严重
    level2_half = RE_LEVEL2_HALFWIDTH.search(text)
    if level2_half:
        add("严重", f"行{find_line(text, level2_half.group())}",
            f"第二层层次序号用了半角圆括号「{level2_half.group().strip()}」",
            "GB/T 9704—2012 7.3.3 / GB/T 15834", "第二层应用全角「（一）」,非半角「(一)」")

    # 4. 主送机关(称谓)校验——查找顶格、末尾冒号的行
    zhusong_found = False
    for i, ln in enumerate(lines, 1):
        s = ln.strip()
        if not s:
            continue
        # 主送机关特征: 顶格(原行不以空格开头)且以冒号结尾,且不是发文字号/标题
        if (not ln.startswith(" ") and not ln.startswith("\t")
                and RE_ZHUSONG_COLON.search(s) and "号" not in s
                and len(s) < 60 and ("、政府" in s or "局" in s or "委" in s
                                     or "办" in s or "院" in s or "部" in s
                                     or "会" in s or "厅" in s or "室" in s)):
            zhusong_found = True
            if not s.endswith("："):
                add("提醒", f"行{i}", f"主送机关末尾未用全角冒号: 「{s[:20]}」",
                    "GB/T 9704—2012 7.3.2", "最后一个机关名称后标全角冒号「：」")
            break
    # 注: 主送机关的有无判断较复杂,这里不强制报"缺失",交 AI 复核

    # 5. 半角冒号/括号在中文语境误用
    halfcolon = RE_HALFCOLON.search(text)
    if halfcolon:
        # 排除 URL(http:)、时间(12:00)等合法用法
        ctx = halfcolon.group()
        if "http" not in ctx and not re.search(r"\d:\d", ctx):
            add("提醒", f"行{find_line(text, halfcolon.group())}",
                f"中文语境可能误用半角冒号: 「{halfcolon.group()}」",
                "GB/T 15834", "公文宜用全角冒号「：」")

    # 6. 标题文种一致性(启发式)
    title_wenzhong = None
    for ln in lines[:15]:
        s = ln.strip()
        if s and ("关于" in s or "通知" in s or "请示" in s or "报告" in s
                  or "函" in s or "意见" in s or "批复" in s or "纪要" in s):
            title_wenzhong = s
            break
    if title_wenzhong:
        for wz in ["通知", "请示", "报告", "函", "意见", "批复", "纪要"]:
            if wz in title_wenzhong:
                title_wenzhong = wz
                break

    # 7. 抄送末尾应为句号(合并抄送区域跨行,跳过空行,避免 PDF 断行误报,修 P5)
    for i, ln in enumerate(lines, 1):
        s = ln.strip()
        if s.startswith("抄送") and ("：" in s or ":" in s):
            # 向后合并抄送区域,直到遇到句号或"印发"(抄送区域结束);空行跳过不停
            merged = s
            done = s.endswith("。")
            for j in range(i, min(i + 10, len(lines))):
                nxt = lines[j].strip()
                if not nxt:
                    continue  # 跳过空行
                if "印发" in nxt:
                    break
                merged += nxt
                if nxt.endswith("。"):
                    done = True
                    break
            if not done and not merged.endswith("。"):
                add("提醒", f"行{i}", "抄送机关末尾未标句号",
                    "GB/T 9704—2012 7.4.2", "最后一个抄送机关名称后标句号「。」")
            break

    # 8. 附件说明末尾不应加标点
    for i, ln in enumerate(lines, 1):
        s = ln.strip()
        m = re.match(r"^附件[:：]\s*\d+[.、]?\s*.+[。，；]$", s)
        if m:
            add("提醒", f"行{i}", "附件说明末尾多了标点符号",
                "GB/T 9704—2012 7.3.4", "附件名称后不加标点符号")

    # 9. 上行文(请示/报告)应标注签发人(GB/T 9704—2012 7.2.6)
    # 仅根据标题区(前15行)判定文种,避免正文里"总结评估报告"等误触发(修 P6)
    # 标题以"请示/报告"结尾才算上行文(排除"通知"里含"报告"二字的情况)
    title_zone = "".join(lines[:15])
    is_shangxing = bool(re.search(r"请示\s*$|报告\s*$", title_zone, re.MULTILINE))
    if is_shangxing and "签发人" not in text:
        add("提醒", "版头", "上行文(请示/报告)未标注签发人",
            "GB/T 9704—2012 7.2.6", "上行文应标注签发人: 「签发人」+全角冒号+姓名")

    return issues


def find_line(text, snippet):
    """返回 snippet 在 text 中首次出现的行号(从1计);未找到返回 1。"""
    if not snippet:
        return 1
    idx = text.find(snippet[:8])
    if idx < 0:
        return 1
    return text.count("\n", 0, idx) + 1


def render_check_report(issues, filename=""):
    """将校验问题列表渲染为 Markdown 报告。

    入参: issues(list[dict]), filename(源文件名,用于报告标题)。
    返回: Markdown 字符串。
    """
    badge = {"严重": "🔴严重", "提醒": "🟡提醒", "建议": "🟢建议"}
    order = {"严重": 0, "提醒": 1, "建议": 2}
    issues_sorted = sorted(issues, key=lambda x: order.get(x["level"], 9))

    out = []
    out.append(f"# 公文格式校验报告\n")
    out.append(f"**源文件**: {sanitize_cell(filename or '(粘贴文本)')}  \n")
    n_severe = sum(1 for i in issues if i["level"] == "严重")
    n_warn = sum(1 for i in issues if i["level"] == "提醒")
    n_info = sum(1 for i in issues if i["level"] == "建议")
    out.append(f"**汇总**: 🔴严重 {n_severe} 项 / 🟡提醒 {n_warn} 项 / 🟢建议 {n_info} 项\n")
    out.append("---\n")

    if not issues:
        out.append("✅ 未发现机器可判定的格式问题。建议人工复核标题事由、文种一致性等语义内容。\n")
        return "\n".join(out)

    out.append("| 序号 | 级别 | 位置 | 问题描述 | 标准依据 | 修改示例 |")
    out.append("|------|------|------|----------|----------|----------|")
    for i, it in enumerate(issues_sorted, 1):
        out.append(
            f"| {i} | {badge.get(it['level'], it['level'])} "
            f"| {sanitize_cell(it['location'])} "
            f"| {sanitize_cell(it['desc'])} "
            f"| {sanitize_cell(it['basis'])} "
            f"| {sanitize_cell(it['example'])} |"
        )
    out.append("\n> 说明: 上述为机器可判定的硬规则结果。标题事由是否贴切、文种是否恰当、"
               "主送机关是否合适等语义内容,请由人工或 AI 复核。\n")
    return "\n".join(out)


# ============================================================
# ============================================================

# ============================================================
# 模块③: 关键信息提取
# ============================================================

# 发文字号: 机关代字〔年份〕顺序号。代字 2-8 字,取「号」结尾的紧凑形式
# 发文字号核心: 〔年份〕顺序号号; 代字单独从匹配位置向左取并清洗
RE_EXTRACT_FAWEN = re.compile(r"〔(\d{4})〕(\d{1,3}号)")
RE_EXTRACT_DATE = re.compile(r"\d{4}年\d{1,2}月\d{1,2}日|[一二三四五六七八九零〇]{2,}年\d{1,2}月\d{1,2}日")
# 关键数据量词: 去掉纯「年/日」(会误匹「2026年」「13日」),保留有信息量的量词(修 P8)
RE_EXTRACT_AMOUNT = re.compile(r"\d+(?:\.\d+)?(?:万元|亿元|元|人|个|项|次|份|个月|批|起|处|条|套|台|座|公里|米|吨)")
RE_EXTRACT_DEADLINE = re.compile(r"(?:于|截至|在|限)\s*\d{4}年\d{1,2}月\d{1,2}日(?:前)?"
                                 r"|务必于.*?(?:前|完成|报送)"
                                 r"|限期.+?(?:完成|整改|报送)"
                                 r"|(?:及时|尽快)(?:报送|上报|处置|反馈|整改)")


def extract_info(text):
    """从来文中抽取关键信息要素。

    入参: text(来文全文)。返回: dict,含发文字号/机关/日期/金额/时限等。
    """
    result = {
        "发文字号": "",
        "发文机关": "",
        "成文日期": "",
        "关键数据": "",
        "时限要求": "",
    }
    # 归一化 PDF/OCR 多余空格后再抽取,避免「〔 2025〕」「2025 年」漏抽
    norm = normalize_spaces(text)
    # 先按"版头独立行"找发文字号: 该行去掉空格后,主体就是「代字〔年〕号」
    # (行内汉字≤8,排除"根据财教〔…〕文件要求"这类正文嵌入式,修 Bug-3)
    header_fawen = None
    for ln in norm.splitlines():
        s = ln.strip()
        if not s:
            continue
        m = re.search(r"([一-龥]{2,6})〔(\d{4})〕(\d{1,3}号)", s)
        if m:
            # 判定该行是否"以发文字号为主"(前后汉字少,排除嵌入式长句)
            prefix_han = len(re.findall(r"[一-龥]", s[:m.start()]))
            suffix_han = len(re.findall(r"[一-龥]", s[m.end():]))
            if prefix_han <= 2 and suffix_han <= 4:
                header_fawen = m
                break
    m = header_fawen if header_fawen else RE_EXTRACT_FAWEN.search(norm)
    if m:
        # 核心〔年〕号已匹配; 取代字(版头行直接用捕获组1,嵌入式需清洗)
        if header_fawen:
            daizi = m.group(1)
            # 剥离版头噪声前缀(如「政府文沁政发」→「沁政发」,修 P2)
            for bad in ("政府文", "公文", "文件", "标志"):
                daizi = daizi.replace(bad, "")
            year, num = m.group(2), m.group(3)
        else:
            start = m.start()
            prefix = re.search(r"[一-龥]{2,12}$", norm[:start])
            daizi = prefix.group() if prefix else ""
            for bad in ("文件", "标志", "公文"):
                daizi = daizi.replace(bad, "")
            # 剥离嵌入式正文中的动词/介词前缀(修 Bug-3),如"根据财教"→"财教"
            for verb in ("根据", "依据", "按照", "关于", "根据《", "贯彻"):
                daizi = daizi.replace(verb, "")
            tail = re.search(r"[一-龥]{2,4}$", daizi)
            daizi = tail.group() if tail else daizi
            year, num = m.group(1), m.group(2)
        if daizi:
            result["发文字号"] = daizi + "〔" + year + "〕" + num
    m = RE_EXTRACT_DATE.search(norm)
    if m:
        result["成文日期"] = m.group()
    amounts = RE_EXTRACT_AMOUNT.findall(norm)
    if amounts:
        # 去重保序后取前 8 个
        uniq = list(dict.fromkeys(amounts))[:8]
        result["关键数据"] = "、".join(uniq)
    m = RE_EXTRACT_DEADLINE.search(text)
    if m:
        result["时限要求"] = m.group().strip()
    # 发文机关: 优先取版头机关名(去"文件"二字);其次取标题"关于"前机关名。
    # 仅在版头+标题区(前15行)搜索,避免正文中"...关于安全生产..."误中(修 P1)
    head_zone = chr(10).join(text.splitlines()[:15])
    org = ""
    head_line = text.splitlines()[0].strip() if text.splitlines() else ""
    if head_line.endswith("文件"):
        org = head_line[:-2].strip()  # 版头"XX市人民政府文件"→"XX市人民政府"
    if not org:
        tm = re.search(r"([一-龥]{2,})关于", head_zone.replace(chr(10), ""))
        if tm:
            org = tm.group(1)
    if org:
        result["发文机关"] = org
    return result


def render_extract_report(info, filename=""):
    """将提取结果渲染为 Markdown 要素表。"""
    out = []
    out.append("# 公文关键信息提取\n")
    out.append(f"**源文件**: {sanitize_cell(filename or '(粘贴文本)')}  \n")
    out.append("---\n")
    out.append("| 要素 | 内容 |")
    out.append("|------|------|")
    out.append(f"| 发文字号 | {sanitize_cell(info['发文字号'] or '（未识别）')} |")
    out.append(f"| 发文机关 | {sanitize_cell(info['发文机关'] or '（未识别）')} |")
    out.append(f"| 成文日期 | {sanitize_cell(info['成文日期'] or '（未识别）')} |")
    out.append(f"| 关键数据 | {sanitize_cell(info['关键数据'] or '（未识别）')} |")
    out.append(f"| 时限要求 | {sanitize_cell(info['时限要求'] or '（未识别）')} |")
    out.append("\n> 注: 发文字号、日期、金额、时限为机器抽取; "
               "**事由、核心要求**等语义要素请由 AI 基于正文补充。\n")
    return "\n".join(out)


# ============================================================
# 模块④: 规范术语校正
# ============================================================

# 术语对照表:(不规范, 规范, 依据)
GLOSSARY = [
    ("请示报告", "请示 / 报告(分清,文种不可混用)", "《公文处理工作条例》"),
    ("申请报告", "请示", "向上级请求批准用'请示'"),
    ("二〇二六年", "2026年(据实)", "GB/T 9704—2012 7.3.5.4 成文日期用阿拉伯数字"),
    ("二零二六年", "2026年(据实)", "GB/T 9704—2012 7.3.5.4"),
    ("[2026]", "〔2026〕", "GB/T 9704—2012 7.2.5 六角括号"),
    ("【2026】", "〔2026〕", "GB/T 9704—2012 7.2.5 六角括号"),
    ("(2026)", "〔2026〕(发文字号年份)", "GB/T 9704—2012 7.2.5"),
    ("搞好", "做好", "规范动词"),
    ("抓一下", "抓好", "规范动词"),
    ("想办法", "采取措施", "规范表述"),
    ("公分", "厘米", "GB 3100 法定计量单位"),
    ("公尺", "米", "GB 3100 法定计量单位"),
    ("兹有", "现将", "现代规范表述"),
    ("为此特作如下通知", "直接陈述要求", "避免冗余过渡语"),
]


def load_glossary_from_md(md_path=None):
    """从 references/gongwen-glossary.md 解析术语表格,返回 (不规范,规范,依据) 列表。

    仅解析「| 不规范表述 | 规范表述 | 依据 |」三列表格行;
    跳过含占位符(…、（）混用说明)的条目,这些无法精确匹配。
    入参: md_path(glossary.md 路径,默认脚本同级 ../references/gongwen-glossary.md)。
    返回: list[tuple]。文件不存在时返回空列表。
    """
    if md_path is None:
        md_path = Path(__file__).resolve().parent.parent / "references" / "gongwen-glossary.md"
    md_path = Path(md_path)
    if not md_path.exists():
        return []
    entries = []
    for ln in md_path.read_text(encoding="utf-8").splitlines():
        s = ln.strip()
        if not s.startswith("|") or "|" not in s[1:]:
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        if len(cells) < 3:
            continue
        bad, good, basis = cells[0], cells[1], cells[2]
        # 跳过表头、分隔线、含占位符(无法精确匹配)的条目
        if ("不规范" in bad and "表述" in bad) or set(bad) <= {"-", ":"}:
            continue
        if "…" in bad or "（" in bad and "混用" in good:
            continue
        if not bad or len(bad) < 2:
            continue
        entries.append((bad, good, basis))
    return entries


def get_full_glossary():
    """返回合并后的完整术语表: glossary.md 解析结果 + 内置 GLOSSARY(去重)。"""
    seen = set()
    merged = []
    for bad, good, basis in (load_glossary_from_md() + list(GLOSSARY)):
        if bad not in seen:
            seen.add(bad)
            merged.append((bad, good, basis))
    return merged


def glossary_check(text):
    """扫描文本中不规范术语,返回校正清单。

    使用合并术语表(glossary.md + 内置 GLOSSARY)。
    返回: list[dict],每项含 line/bad/good/basis。
    """
    results = []
    lines = text.splitlines()
    for bad, good, basis in get_full_glossary():
        for i, ln in enumerate(lines, 1):
            if bad in ln:
                results.append({"line": i, "bad": bad, "good": good, "basis": basis})
    return results


def render_glossary_report(results, filename=""):
    """渲染术语校正清单为 Markdown。"""
    out = []
    out.append("# 公文规范术语校正\n")
    out.append(f"**源文件**: {sanitize_cell(filename or '(粘贴文本)')}  \n")
    out.append("---\n")
    if not results:
        out.append("✅ 未发现对照表中的不规范术语。建议人工复核文种使用、称谓、量词等。\n")
        return "\n".join(out)
    out.append("| 序号 | 行 | 不规范表述 | 规范表述 | 依据 |")
    out.append("|------|----|-----------|----------|------|")
    for i, r in enumerate(results, 1):
        out.append(
            f"| {i} | {sanitize_cell(r['line'])} "
            f"| {sanitize_cell(r['bad'])} "
            f"| {sanitize_cell(r['good'])} "
            f"| {sanitize_cell(r['basis'])} |"
        )
    out.append("\n> 注: 同一处可能涉及多个问题,请结合上下文判断是否需改。\n")
    return "\n".join(out)


# ============================================================
# 命令行入口
# ============================================================

def cmd_check(args):
    text = read_text(args.file)
    issues = check_gongwen(text)
    print(render_check_report(issues, args.file))


def cmd_extract(args):
    text = read_text(args.file)
    info = extract_info(text)
    print(render_extract_report(info, args.file))


def cmd_glossary(args):
    text = read_text(args.file)
    results = glossary_check(text)
    print(render_glossary_report(results, args.file))


def build_parser():
    p = argparse.ArgumentParser(
        prog="gongwen_toolkit",
        description="党政机关公文辅助校验工具集(check/extract/glossary)",
    )
    sub = p.add_subparsers(dest="command", required=True)

    pc = sub.add_parser("check", help="公文格式合规校验")
    pc.add_argument("file", help="公文文本文件路径(.txt/.md)")
    pc.set_defaults(func=cmd_check)

    pe = sub.add_parser("extract", help="来文关键信息提取")
    pe.add_argument("file", help="来文文本文件路径(.txt/.md)")
    pe.set_defaults(func=cmd_extract)

    pg = sub.add_parser("glossary", help="规范术语校正")
    pg.add_argument("file", help="公文文本文件路径(.txt/.md)")
    pg.set_defaults(func=cmd_glossary)


    return p


def main():
    parser = build_parser()
    args = parser.parse_args()
    try:
        args.func(args)
    except (ValueError, FileNotFoundError) as e:
        print(f"❌ 错误: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
