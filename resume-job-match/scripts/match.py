#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
简历-JD 匹配分析脚本（parse / parse-jd / score 三合一）。

功能: 对简历与 JD 文本做确定性的结构化抽取与机器可判定匹配
     (技能词库命中/年限数值比对/学历比对/证书比对),
     供 AI 在匹配评分与差距诊断环节调用,保证可复现。
创建日期: 2026-08-03

输入: 命令行参数 <子命令> <文件路径> [JD路径]
  子命令:
    parse     <简历>        抽取简历要素(基本信息PII脱敏/教育/经历/技能/项目/证书)
    parse-jd  <JD>          抽取 JD 要素(岗位名/硬性要求/加分项)
    score     <简历> <JD>   机器可判定的匹配(技能命中/年限/学历/证书) + 评分骨架

输出: 标准 JSON 文本( stdout ),字段含义见各函数注释。
     ① parse     -> basic{脱敏}, education[], experience[], skills[], projects[], certs[]
     ② parse-jd  -> title, hard{学历/年限/技能/证书}, plus{技能/软性}
     ③ score     -> skill_hits{必备命中/总数, 加分命中/总数}, year_match,
                    edu_match, cert_hits, machine_score(骨架,语义项留空由AI填)
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
THESAURUS = os.path.join(HERE, "..", "references", "skill-thesaurus.md")


# ---------- 工具:读取文本 ----------

def read_text(path):
    """读取 txt/md/docx 为纯文本。docx 需可选依赖 python-docx。"""
    if not os.path.exists(path):
        raise FileNotFoundError(f"文件不存在: {path}")
    low = path.lower()
    if low.endswith((".txt", ".md")):
        with open(path, "r", encoding="utf-8-sig") as f:
            return f.read()
    if low.endswith(".docx"):
        try:
            from docx import Document
        except ImportError:
            raise ValueError(
                "读取 docx 需要可选依赖 python-docx,未安装。请粘贴简历/JD 文本或另存为 txt。"
            )
        doc = Document(path)
        return "\n".join(p.text for p in doc.paragraphs)
    if low.endswith(".csv"):
        with open(path, "r", encoding="utf-8-sig") as f:
            return f.read()
    # 兜底按文本读
    with open(path, "r", encoding="utf-8-sig", errors="ignore") as f:
        return f.read()


# ---------- PII 脱敏 ----------

def mask_phone(text):
    """手机号脱敏: 13812345678 -> 138****5678。"""
    return re.sub(r"(?<!\d)(1[3-9]\d)\d{4}(\d{4})(?!\d)", r"\1****\2", text)


def mask_email(text):
    """邮箱脱敏: abc@example.com -> a***@example.com。"""
    return re.sub(r"([A-Za-z0-9._%+-])[A-Za-z0-9._%+-]*@([A-Za-z0-9.-]+)",
                  r"\1***@\2", text)


def mask_idcard(text):
    """身份证号脱敏: 保留前6后4。"""
    return re.sub(r"(?<!\d)(\d{6})\d{8,10}(\d{4})(?!\d)", r"\1********\2", text)


def mask_all(text):
    """对文本做手机/邮箱/身份证脱敏。"""
    text = mask_idcard(text)
    text = mask_phone(text)
    text = mask_email(text)
    return text


# ---------- 技能词库 ----------

def load_thesaurus():
    """解析 skill-thesaurus.md 为 {规范名: [别名列表]}。

    解析 markdown 表格,首列为规范名,第二列为别名(顿号/斜杠/逗号分隔)。
    失败则用内置最小词库兜底。
    """
    table = {}
    fallback = {
        "python": ["py", "python3"],
        "java": ["java8", "java11", "jdk", "j2ee"],
        "spring": ["spring framework", "springframework"],
        "spring boot": ["springboot"],
        "spring cloud": ["springcloud"],
        "mysql": [],
        "redis": [],
        "docker": [],
        "kubernetes": ["k8s"],
        "kafka": [],
        "elasticsearch": ["es", "elastic"],
    }
    try:
        with open(THESAURUS, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line.startswith("|") or "---" in line:
                    continue
                cells = [c.strip() for c in line.strip("|").split("|")]
                if len(cells) < 2:
                    continue
                key = cells[0].strip().lower()
                if not key or key in ("规范名", "加分项", "类型"):
                    continue
                aliases = re.split(r"[、,，/]", cells[1]) if len(cells) > 1 else []
                aliases = [a.strip().lower() for a in aliases if a.strip()]
                table[key] = list(set(aliases + [key]))
    except Exception:
        return fallback
    if not table:
        return fallback
    return table


def match_skills(text, thesaurus):
    """在 text(小写) 中匹配技能词库,返回命中的规范名集合。

    入参: text 原始文本, thesaurus {规范名:[别名]}。
    返回: set[str] 命中的规范名(去重)。

    规则(防误判):
      1. 词边界匹配: 技能词前后须是非字母数字(避免 '无java经验' 命中 java);
         中文技能词(如 微服务/软考)不受词边界限制。
      2. 否定语境排除: 技能词前紧邻 '无/没有/不会/未/不含/不用/不熟' 时,视为不具备,不计入。
    """
    low = text.lower()
    hit = set()
    neg_words = ("无", "没有", "不会", "未", "不含", "不用", "不熟", "不懂")
    for canon, aliases in thesaurus.items():
        for a in aliases:
            if not a:
                continue
            if re.fullmatch(r"[A-Za-z0-9.+#-]+", a):
                # 英文/符号型技能: 用前后非字母数字边界(避免 '无java经验' 命中)
                pat = re.compile(r"(?<![A-Za-z0-9])" + re.escape(a) + r"(?![A-Za-z0-9])")
            else:
                # 含中文: 直接子串
                pat = re.compile(re.escape(a))
            for m in pat.finditer(low):
                # 否定语境排除: 技能词前 6 字符内以否定词结尾(允许中间有标点/空格)
                prefix = low[max(0, m.start() - 6):m.start()].rstrip(" ,，、。.:；; \t")
                if any(prefix.endswith(w) for w in neg_words):
                    continue
                hit.add(canon)
                break
    return hit


# ---------- 简历解析 ----------

def parse_resume(text):
    """抽取简历要素。返回 dict。文本先做 PII 脱敏再返回。"""
    masked = mask_all(text)
    thesaurus = load_thesaurus()

    # 基本信息
    phone = re.search(r"(?<!\d)(1[3-9]\d{9})(?!\d)", text)
    email = re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", text)
    name = None
    m = re.search(r"姓\s*名[:：\s]*([一-龥A-Za-z·]{2,8})", text)
    if m:
        name = m.group(1).strip()

    # 学历
    edu_keywords = {"博士": "博士", "硕士|研究生|msc|master": "硕士",
                    "本科|学士|bachelor|bsc": "本科", "大专|专科|专科": "大专"}
    edu_level = None
    for pat, lvl in edu_keywords.items():
        if re.search(pat, text, re.IGNORECASE):
            edu_level = lvl
            break

    # 工作年限: 优先显式表述(工作年限:5年 / 5年工作经验 / 5年经验),否则按时间段累计
    years = None
    ym = re.search(r"(?:工作年限|经验|经历)[:：\s]*(\d+)\s*年", text)
    if not ym:
        ym = re.search(r"(\d+)\s*年(?:以上)?(?:工作)?(?:经验|经历)", text)
    if ym:
        years = int(ym.group(1))
    if years is None:
        # 按时间段 2017.09-2021.06 累计(粗略,重叠不扣)
        spans = re.findall(r"(20\d{2})\s*[.\-/年]\s*\d{1,2}\s*[.\-/]?\s*(?:至|~|-|—)\s*(20\d{2}|至今|现在|present)",
                           text)
        total = 0
        cur_year = 2026
        for s, e in spans:
            try:
                si = int(s)
                ei = int(e) if e.isdigit() else cur_year
                total += max(0, ei - si)
            except ValueError:
                continue
        if total > 0:
            years = total

    skills = sorted(match_skills(text, thesaurus))

    # 项目经历(粗略:按"项目"关键字分段)
    projects = []
    for line in text.splitlines():
        ls = line.strip()
        if re.match(r"^\d+[.、\)）]\s*", ls) and ("项目" in ls or len(ls) > 6):
            projects.append(ls)

    # 证书
    cert_lib = {"cpa": r"cpa|注册会计师", "pmp": r"pmp|项目管理",
                "软考": r"软考|软件设计师|系统分析师|计算机技术与软件",
                "六西格玛": r"六西格玛|six\s*sigma", "cfa": r"\bcfa\b|特许金融分析师"}
    certs = [c for c, pat in cert_lib.items() if re.search(pat, text, re.IGNORECASE)]

    return {
        "basic": {
            "name": name,
            "phone": mask_phone(phone.group(0)) if phone else None,
            "email": mask_email(email.group(0)) if email else None,
        },
        "education_level": edu_level,
        "work_years": years,
        "skills": skills,
        "projects": projects,
        "certs": certs,
        "_masked_text_preview": masked[:200],
    }


# ---------- JD 解析 ----------

def parse_jd(text):
    """抽取 JD 要素。返回 dict。"""
    thesaurus = load_thesaurus()
    low = text.lower()

    # 岗位名
    title = None
    tm = re.search(r"(?:招聘岗位|岗位名称|职位|职位名称)[:：\s]*([^\n]+)", text)
    if tm:
        title = tm.group(1).strip()
    if not title:
        tm2 = re.search(r"([一-龥A-Za-z/]{2,20}(?:工程师|开发|经理|专员|分析师|架构师))", text)
        title = tm2.group(1).strip() if tm2 else None

    # 硬性区段: 抓"任职要求/硬性/要求" 到 下一个标题 之间的文本
    hard_text = _section(text, ["任职要求", "硬性", "任职资格", "岗位要求", "要求"])
    plus_text = _section(text, ["加分项", "优先", "加分"])

    # 学历要求
    edu_req = None
    if re.search(r"博士", text):
        edu_req = "博士"
    elif re.search(r"硕士|研究生|master", text, re.IGNORECASE):
        edu_req = "硕士"
    elif re.search(r"本科|学士|bachelor", text, re.IGNORECASE):
        edu_req = "本科"
    elif re.search(r"大专|专科", text):
        edu_req = "大专"

    # 年限要求
    year_req = None
    ym = re.search(r"(\d+)\s*年(?:以上|及以上|以上经验)?", text)
    if ym:
        year_req = int(ym.group(1))

    # 技能: 全文命中作为候选,硬性区命中标 hard,加分区命中标 plus
    all_hit = match_skills(text, thesaurus)
    hard_hit = match_skills(hard_text, thesaurus) if hard_text else set()
    plus_hit = match_skills(plus_text, thesaurus) if plus_text else set()
    # 加分区未覆盖的命中默认归硬性(常见 JD 把必备写在任职要求里)
    hard_skills = sorted((all_hit - plus_hit) | hard_hit)
    plus_skills = sorted(plus_hit)

    # 证书要求
    cert_lib = {"cpa": r"cpa|注册会计师", "pmp": r"pmp", "软考": r"软考", "cfa": r"\bcfa\b"}
    cert_req = [c for c, pat in cert_lib.items() if re.search(pat, text, re.IGNORECASE)]

    return {
        "title": title,
        "hard": {
            "edu": edu_req,
            "years": year_req,
            "skills": hard_skills,
            "certs": cert_req,
        },
        "plus": {
            "skills": plus_skills,
        },
    }


def _section(text, keywords):
    """从 text 中抓取"关键词所在行到下一个空行/标题"之间的内容。"""
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if any(k in line for k in keywords) and ("：" in line or ":" in line or i == len(lines) - 1):
            chunk = []
            for j in range(i + 1, min(i + 40, len(lines))):
                lj = lines[j].strip()
                # 遇到下一个标题段就停
                if lj and re.match(r"^(薪资|工作地点|岗位职责|任职要求|加分项|优先项|职位|岗位)[：:]", lj):
                    break
                if lj:
                    chunk.append(lj)
            if chunk:
                return "\n".join(chunk)
    return ""


# ---------- 评分 ----------

EDU_RANK = {"大专": 1, "本科": 2, "硕士": 3, "博士": 4}


def cmd_score(resume_path, jd_path):
    """机器可判定的匹配 + 评分骨架。

    语义项(项目相关性)留空,由 AI 在报告里补。
    硬性条件任一完全不满足 -> pass_hard=False。
    """
    rtext = read_text(resume_path)
    jtext = read_text(jd_path)
    resume = parse_resume(rtext)
    jd = parse_jd(jtext)

    hard = jd["hard"]

    # 硬性: 学历
    edu_pass = True
    if hard["edu"] and resume["education_level"]:
        edu_pass = EDU_RANK.get(resume["education_level"], 0) >= EDU_RANK.get(hard["edu"], 0)
    elif hard["edu"] and not resume["education_level"]:
        edu_pass = None  # 未提及,无法判定

    # 硬性: 年限
    year_pass = True
    year_score = 100
    if hard["years"]:
        ry = resume["work_years"] or 0
        if ry == 0 and resume["work_years"] is None:
            year_pass = None
        else:
            year_pass = ry >= hard["years"]
            # 评分: 达标100, 每少1年扣20
            year_score = max(0, 100 - max(0, hard["years"] - ry) * 20)

    # 硬性: 必备技能
    rset = set(resume["skills"])
    hset = set(hard["skills"])
    hard_hit = sorted(hset & rset)
    hard_miss = sorted(hset - rset)
    skill_cov = round(len(hard_hit) / len(hset) * 100, 1) if hset else 100.0
    skill_pass = len(hard_miss) == 0 if hset else True

    # 硬性: 证书
    cert_hit = sorted(set(hard["certs"]) & set(resume["certs"]))
    cert_miss = sorted(set(hard["certs"]) - set(resume["certs"]))
    cert_pass = len(cert_miss) == 0

    # pass_hard: 任一明确 False 则 False,None 不算失败但需提示
    flags = [edu_pass, year_pass, skill_pass, cert_pass]
    pass_hard = not any(f is False for f in flags)
    unjudged = any(f is None for f in flags)

    # 加分技能
    pset = set(jd["plus"]["skills"])
    plus_hit = sorted(pset & rset)
    plus_cov = round(len(plus_hit) / len(pset) * 100, 1) if pset else 0.0

    # 机器评分骨架(语义相关性项留空, weight=20%)
    edu_score = 100 if edu_pass else (0 if edu_pass is False else 0)
    if edu_pass and resume["education_level"] and hard["edu"]:
        edu_score = 100 if EDU_RANK[resume["education_level"]] >= EDU_RANK[hard["edu"]] else 0

    machine_score = {
        "edu": {"weight": 15, "score": edu_score, "basis": f"简历{resume['education_level']} vs JD{hard['edu']}"},
        "years": {"weight": 20, "score": year_score, "basis": f"简历{resume['work_years']}年 vs JD要求{hard['years']}年"},
        "skills": {"weight": 35, "score": skill_cov, "basis": f"必备命中{len(hard_hit)}/{len(hset)}"},
        "relevance": {"weight": 20, "score": None, "basis": "AI语义判断(项目/经历相关性)"},
        "plus": {"weight": 10, "score": plus_cov, "basis": f"加分命中{len(plus_hit)}/{len(pset)}"},
    }
    # 已知项加权(相关性未填先按0占位,提示AI补)
    known = {k: v for k, v in machine_score.items() if v["score"] is not None}
    total_w = sum(v["weight"] for v in known.values())
    weighted = sum(v["score"] * v["weight"] for v in known.values())
    prelim = round(weighted / total_w, 1) if total_w else 0

    return {
        "resume_summary": {
            "education_level": resume["education_level"],
            "work_years": resume["work_years"],
            "skills": resume["skills"],
            "certs": resume["certs"],
        },
        "jd_summary": {
            "title": jd["title"],
            "hard": hard,
            "plus_skills": jd["plus"]["skills"],
        },
        "skill_hits": {
            "hard_hit": hard_hit,
            "hard_miss": hard_miss,
            "plus_hit": plus_hit,
            "hard_coverage_pct": skill_cov,
            "plus_coverage_pct": plus_cov,
        },
        "year_match": {"resume": resume["work_years"], "req": hard["years"], "pass": year_pass, "score": year_score},
        "edu_match": {"resume": resume["education_level"], "req": hard["edu"], "pass": edu_pass},
        "cert_hits": {"hit": cert_hit, "miss": cert_miss},
        "pass_hard": pass_hard,
        "has_unjudged": unjudged,
        "machine_score": machine_score,
        "preliminary_score_pct": prelim,
        "note": "preliminary_score 不含语义相关性项(权重20%),AI 需补 relevance.score 后重算综合分。",
    }


# ---------- sanitize(供 AI 写报告参照) ----------

def sanitize_cell(value):
    """净化动态字段,防破坏 Markdown 表格与注入(同 analyze.py 规则)。"""
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
        print(json.dumps({"error": "用法: python match.py <parse|parse-jd|score> <文件> [JD]"},
                         ensure_ascii=False))
        sys.exit(2)
    cmd = sys.argv[1]
    try:
        if cmd == "parse":
            result = parse_resume(read_text(sys.argv[2]))
        elif cmd == "parse-jd":
            result = parse_jd(read_text(sys.argv[2]))
        elif cmd == "score":
            if len(sys.argv) < 4:
                result = {"error": "score 需要两个参数: <简历> <JD>"}
            else:
                result = cmd_score(sys.argv[2], sys.argv[3])
        else:
            result = {"error": f"未知子命令: {cmd}(应为 parse/parse-jd/score)"}
    except FileNotFoundError as e:
        result = {"error": str(e)}
    except ValueError as e:
        result = {"error": str(e)}
    except Exception as e:
        result = {"error": f"分析失败: {type(e).__name__}: {e}"}
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
