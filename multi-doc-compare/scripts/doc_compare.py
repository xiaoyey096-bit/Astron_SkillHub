#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
多文档对比脚本（parse / matrix / diff 三合一）。

功能: 切分多份文档、提取可对比维度、生成对比矩阵候选、识别关键词层面的
     共识/分歧/独有信息。供 AI 在对比报告环节调用,保证可复现;
     维度归类与语义级共识/分歧判断由 AI 完成。
创建日期: 2026-08-03

输入: python doc_compare.py <子命令> <文件>
  子命令:
    parse    <文件>   按 ===文档X=== 切分, 提取每份的标题/关键词/维度候选
    matrix   <文件>   汇总维度并集, 生成对比矩阵候选(每文档每维度的命中内容)
    diff     <文件>   关键词层面: 哪些所有文档都命中(共识候选)、哪些仅一份命中(独有候选)

输出: 标准 JSON( stdout )。
"""

import sys
import os
import re
import json
from collections import defaultdict

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def read_input(arg):
    if os.path.exists(arg) and os.path.isfile(arg):
        with open(arg, "r", encoding="utf-8-sig") as f:
            return f.read()
    return arg


# 通用维度关键词库(规范维度 -> 关键词列表)
DIM_KEYWORDS = {
    "价格": ["价格", "售价", "费用", "收费", "定价", "多少钱", "免费", "付费", "元/月", "套餐"],
    "功能": ["功能", "支持", "特性", "能力", "模块"],
    "平台/兼容": ["平台", "兼容", "Windows", "Mac", "iOS", "安卓", "Linux", "支持系统"],
    "优点": ["优点", "优势", "亮点", "长处", "好处"],
    "缺点": ["缺点", "不足", "劣势", "短板", "限制", "问题"],
    "特色": ["特色", "独有", "独特", "专属"],
    "适用对象": ["适用", "适合", "面向", "目标用户", "人群"],
}


def split_docs(text):
    """按 ===文档X=== 或 === 标题 === 切分多份文档。返回 [(名称, 正文), ...]。"""
    # 匹配 ===文档A：xxx=== 或 ===xxx===
    parts = re.split(r"(={3,}\s*[^=\n]{1,40}\s*={3,})", text)
    docs = []
    if len(parts) <= 1:
        # 无分隔符, 整体作为一份(但本 Skill 需多份, 调用方会提示)
        return [("文档1", text.strip())] if text.strip() else []
    # parts[0] 是首个分隔符前的内容(通常为空), 之后 间隔为 [分隔符, 正文, 分隔符, 正文...]
    i = 1
    while i < len(parts):
        header = parts[i].strip().strip("=").strip()
        body = parts[i + 1].strip() if i + 1 < len(parts) else ""
        name = header.split("：")[0].split(":")[0].strip() if header else f"文档{len(docs)+1}"
        docs.append((name, body))
        i += 2
    return docs


def extract_dims(body):
    """从单份文档提取命中的维度(规范维度名列表) + 各维度命中片段。

    优先取"维度关键词 + 冒号/：'"形式的标题行(如"价格：30元/月"),
    避免抓到该词在无关行的首次出现。
    """
    hits = defaultdict(list)
    lines = body.splitlines()
    for dim, kws in DIM_KEYWORDS.items():
        matched_lines = []
        # 先找"关键词：内容"的标题行(最可靠)
        for line in lines:
            ls = line.strip()
            if not ls:
                continue
            for kw in kws:
                if re.search(re.escape(kw) + r"\s*[：:]", ls):
                    matched_lines.append(ls)
                    break
        # 若无标题行命中, 再退回全文任意命中(取所在行)
        if not matched_lines:
            for kw in kws:
                for m in re.finditer(re.escape(kw), body):
                    start = body.rfind("\n", 0, m.start()) + 1
                    end = body.find("\n", m.end())
                    end = end if end != -1 else len(body)
                    line = body[start:end].strip()
                    if line and line not in matched_lines:
                        matched_lines.append(line)
        for ml in matched_lines:
            hits[dim].append(ml[:80])
    return hits


# ---------- 子命令: parse ----------

def cmd_parse(text):
    docs = split_docs(text)
    result = []
    for name, body in docs:
        hits = extract_dims(body)
        result.append({
            "name": name,
            "length": len(body),
            "dims_hit": list(hits.keys()),
            "dim_content": {k: v[:3] for k, v in hits.items()},
        })
    return {"doc_count": len(docs), "docs": result}


# ---------- 子命令: matrix ----------

def cmd_matrix(text):
    docs = split_docs(text)
    # 维度并集
    all_dims = []
    seen = set()
    doc_dims = []
    for name, body in docs:
        hits = extract_dims(body)
        doc_dims.append((name, hits))
        for d in hits:
            if d not in seen:
                seen.add(d)
                all_dims.append(d)
    # 生成矩阵候选
    matrix = []
    for dim in all_dims:
        row = {"dimension": dim, "cells": {}}
        for name, hits in doc_dims:
            if dim in hits:
                # 取该维度第一行作为代表内容
                row["cells"][name] = hits[dim][0] if hits[dim] else "未提及"
            else:
                row["cells"][name] = "未提及"
        matrix.append(row)
    return {
        "doc_count": len(docs),
        "doc_names": [n for n, _ in doc_dims],
        "dimensions": all_dims,
        "matrix": matrix,
        "note": "matrix 为机器按关键词命中生成, AI 需做维度归一与口径统一, 并复核'未提及'。",
    }


# ---------- 子命令: diff ----------

def cmd_diff(text):
    """关键词层面: 共识候选(所有文档都命中的维度)、独有候选(仅一份命中的维度)。"""
    docs = split_docs(text)
    doc_dims = [(name, set(extract_dims(body).keys())) for name, body in docs]
    all_dim_set = set()
    for _, ds in doc_dims:
        all_dim_set |= ds
    # 共识: 所有文档都命中的维度
    consensus = []
    for d in all_dim_set:
        if all(d in ds for _, ds in doc_dims):
            consensus.append(d)
    # 独有: 仅一份文档命中的维度
    unique = defaultdict(list)
    for d in all_dim_set:
        owners = [name for name, ds in doc_dims if d in ds]
        if len(owners) == 1:
            unique[owners[0]].append(d)
    # 分歧候选: 价格数值差异(粗略)
    conflict_candidates = []
    for name, body in docs:
        vals = re.findall(r"(\d+(?:\.\d+)?)\s*元", body)
        if vals:
            conflict_candidates.append({"doc": name, "price_values": vals})

    # 差异内容候选: 同一维度被多份文档命中, 但各自内容文本不同(供 AI 判独有/分歧)
    # 取每个文档在每个维度的代表内容, 不同则记为"内容差异候选"
    doc_dim_content = []
    for name, body in docs:
        hits = extract_dims(body)
        for dim, lines in hits.items():
            doc_dim_content.append({"doc": name, "dim": dim, "sample": lines[0] if lines else ""})
    content_diff = defaultdict(list)
    for item in doc_dim_content:
        content_diff[item["dim"]].append((item["doc"], item["sample"]))
    diff_content_candidates = {}
    for dim, entries in content_diff.items():
        samples = set(s for _, s in entries if s)
        # 同维度, 不同文档的内容文本不完全相同 -> 内容差异候选
        if len(entries) >= 2 and len(samples) >= 2:
            diff_content_candidates[dim] = [{"doc": d, "content": s} for d, s in entries]

    return {
        "consensus_candidates": consensus,
        "unique_candidates": {k: v for k, v in unique.items()},
        "conflict_candidates": conflict_candidates,
        "diff_content_candidates": diff_content_candidates,
        "note": "consensus/unique 为维度名层面候选; diff_content 为同维度内容差异(供 AI 判独有/分歧); 均需 AI 语义复核。",
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
        print(json.dumps({"error": "用法: python doc_compare.py <parse|matrix|diff> <文件>"}, ensure_ascii=False))
        sys.exit(2)
    cmd = sys.argv[1]
    try:
        text = read_input(sys.argv[2])
        if cmd == "parse":
            result = cmd_parse(text)
        elif cmd == "matrix":
            result = cmd_matrix(text)
        elif cmd == "diff":
            result = cmd_diff(text)
        else:
            result = {"error": f"未知子命令: {cmd}(应为 parse/matrix/diff)"}
    except Exception as e:
        result = {"error": f"失败: {type(e).__name__}: {e}"}
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
