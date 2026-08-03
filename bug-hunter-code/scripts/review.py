#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
代码静态审查脚本(scan 子命令)。

功能: 对代码文件做多维度确定性扫描——安全漏洞(命令注入/SQL注入/硬编码密钥/
     路径穿越/不安全反序列化/SSL禁用)、缺陷(资源未释放/异常吞没)、坏味道
     (长函数/高复杂度/TODO)。规则定义见 references/security-rules.md 与
     defect-rules.md。供 AI 在审查环节调用,保证可复现;语义级问题由 AI 补。
创建日期: 2026-08-03

输入: python review.py scan <文件路径> [--lang 语言]
输出: 标准 JSON( stdout )。字段:
  ① summary   -> lang, lines, func_count, counts{critical/warning/info}
  ② findings  -> [{id, rule, severity, line, snippet, risk, fix_hint, category}]
  ③ metrics   -> per_function{圈复杂度近似, 行数}, long_functions[], todos[]
"""

import sys
import os
import re
import json
import keyword as _kw

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


# ---------- 读取与语言识别 ----------

def read_code(path):
    if not os.path.exists(path):
        raise FileNotFoundError(f"文件不存在: {path}")
    with open(path, "r", encoding="utf-8-sig", errors="ignore") as f:
        return f.read()


def guess_lang(path, text):
    """按扩展名/特征猜语言。"""
    ext = os.path.splitext(path)[1].lower()
    mapping = {".py": "python", ".js": "javascript", ".mjs": "javascript",
               ".ts": "typescript", ".java": "java", ".go": "go",
               ".rs": "rust", ".c": "c", ".cpp": "c", ".h": "c"}
    if ext in mapping:
        return mapping[ext]
    if "def " in text and "import " in text:
        return "python"
    if "function " in text or "const " in text:
        return "javascript"
    if "public class" in text or "System.out" in text:
        return "java"
    return "unknown"


# ---------- 占位符豁免(密钥判定用) ----------

PLACEHOLDER_WORDS = ("your", "example", "sample", "placeholder", "changeme",
                     "replace", "dummy", "mock", "test", "fake", "todo",
                     "xxx", "redacted", "os.environ", "getenv", "process.env")


def is_placeholder(value):
    """判断密钥值是否为占位符(豁免)。"""
    low = value.lower()
    if any(w in low for w in PLACEHOLDER_WORDS):
        return True
    if all(c in "xX*-" for c in value):
        return True
    return False


# ---------- 安全规则 ----------

def scan_security(lines, lang):
    """扫描安全规则,返回 findings 列表。"""
    findings = []
    fid = [0]

    def add(rule, sev, line_no, snippet, risk, fix, category="security"):
        fid[0] += 1
        findings.append({
            "id": fid[0], "rule": rule, "severity": sev, "line": line_no,
            "snippet": snippet, "risk": risk, "fix_hint": fix, "category": category,
        })

    full = "\n".join(lines)

    for i, line in enumerate(lines, start=1):
        # 命令注入: shell=True
        if "shell=True" in line and ("subprocess" in full or "run(" in line or "Popen" in line):
            add("shell-true", "critical", i, _trim(line),
                "shell=True 且可能拼接用户输入,存在命令注入(RCE)风险",
                "改 shell=False 并用参数列表传参")
        # os.system
        if re.search(r"os\.system\s*\(", line) and ("+" in line or "%" in line or "{" in line or "f'" in line):
            add("os-system", "critical", i, _trim(line),
                "os.system 拼接字符串,存在命令注入风险",
                "改 subprocess.run([..], shell=False)")
        # eval/exec
        if re.search(r"\beval\s*\(", line) or re.search(r"\bexec\s*\(", line):
            add("eval-exec", "critical", i, _trim(line),
                "eval/exec 执行动态代码,若处理外部数据有代码注入风险",
                "禁用 eval/exec,改安全解析")
        # SQL 拼接
        if re.search(r"(SELECT|INSERT|UPDATE|DELETE)\s", line, re.IGNORECASE):
            if any(op in line for op in ("%", "+", ".format", "{", "f'", 'f"')):
                add("sql-concat", "critical", i, _trim(line),
                    "SQL 字符串拼接变量,存在 SQL 注入风险",
                    "参数化查询: execute(sql, (var,))")
        # execute("...%s..." % var)
        if re.search(r"execute\s*\([^)]*%", line):
            add("sql-format", "critical", i, _trim(line),
                "execute 用 % 格式化拼 SQL,SQL 注入风险",
                    "改占位符参数化")
        # 硬编码密钥: sk- / AKIA / password= 等
        sk = re.search(r"sk-[A-Za-z0-9]{20,}", line)
        if sk and not is_placeholder(sk.group(0)):
            add("api-key-hardcode", "critical", i, _trim(line),
                "硬编码 API 密钥(sk-),泄露风险",
                "改用环境变量")
        aka = re.search(r"AKIA[A-Z0-9]{16}", line)
        if aka and not is_placeholder(aka.group(0)):
            add("aws-key", "critical", i, _trim(line),
                "硬编码 AWS AccessKey,泄露风险",
                "删除,改环境变量")
        cred = re.search(r"(?i)(password|api_key|apikey|secret|token)\s*[=:]\s*['\"]?([A-Za-z0-9_@./\-]{4,})['\"]?", line)
        if cred:
            name, val = cred.group(1), cred.group(2)
            # 若值本身来自环境变量读取(正确做法),则跳过,不报硬编码
            if re.search(r"(?i)(os\.environ|getenv|process\.env|os\.getenv|System\.getenv|Environment\.getenv)", cred.group(0)):
                pass
            else:
                # 任何写死的凭据字面量都应提示用环境变量:
                #  - 非占位符(疑似真实凭据) -> critical
                #  - 占位符(如 your-api-key-replace-me) -> warning(教学性提醒:即便是占位符,也应改用环境变量)
                if not is_placeholder(val) and not is_placeholder(cred.group(0)):
                    add("password-assign", "critical", i, _trim(line),
                        f"硬编码凭据({name}),疑似真实密钥,泄露风险",
                        "改用环境变量或配置中心")
                else:
                    add("password-assign", "warning", i, _trim(line),
                        f"硬编码凭据字面量({name}),即便是占位符也建议改用环境变量",
                        "改用 os.environ.get('KEY') 或配置中心读取")
        # 不安全反序列化
        if re.search(r"pickle\.loads?\s*\(", line):
            add("pickle-load", "critical", i, _trim(line),
                "pickle 反序列化外部数据可导致 RCE",
                "改用 JSON 等安全格式")
        if re.search(r"yaml\.load\s*\(", line) and "SafeLoader" not in line and "safe_load" not in line:
            add("yaml-unsafe-load", "critical", i, _trim(line),
                "yaml.load 未指定 SafeLoader,可导致任意对象构造",
                "改 yaml.safe_load")
        # SSL 禁用
        if "verify=False" in line or "CERT_NONE" in line or "check_hostname=False" in line:
            add("ssl-verify-false", "warning", i, _trim(line),
                "禁用 SSL 证书验证,存在中间人攻击风险",
                "启用证书验证(删除 verify=False)")
        if "rejectUnauthorized" in line and "false" in line.lower():
            add("tls-reject", "warning", i, _trim(line),
                "Node.js 禁用 TLS 校验",
                "删除 rejectUnauthorized:false")

    # 路径穿越: open(变量) 且全文无 with(粗略)
    for i, line in enumerate(lines, start=1):
        if re.search(r"\bopen\s*\(", line) and re.search(r"open\s*\(\s*[a-zA-Z_]", line):
            if "with " not in line:
                # 检查同函数体内是否有 close(粗略: 往后 15 行)
                window = "\n".join(lines[i - 1:i + 15])
                if ".close()" not in window:
                    findings.append(_mk("path-or-resource", "warning", i, _trim(line),
                                        "open 未用 with 且附近无 close,资源可能未释放(且若路径来自用户有穿越风险)",
                                        "改 with open(..) as f:,并对用户路径过滤 ..",
                                        fid))
    return findings


def _mk(rule, sev, line, snippet, risk, fix, fid_counter, category="defect"):
    fid_counter[0] += 1
    return {"id": fid_counter[0], "rule": rule, "severity": sev, "line": line,
            "snippet": snippet, "risk": risk, "fix_hint": fix, "category": category}


def _trim(s, n=60):
    s = s.strip()
    return s if len(s) <= n else s[:n] + "..."


# ---------- 缺陷与坏味道 ----------

def scan_defects(lines, lang):
    findings = []
    fid = [0]

    for i, line in enumerate(lines, start=1):
        stripped = line.strip()
        # 裸 except
        if re.match(r"except\s*:", stripped):
            findings.append(_mk("bare-except", "warning", i, _trim(line),
                                "裸 except 捕获所有异常(含 KeyboardInterrupt/SystemExit),易掩盖错误",
                                "改 except Exception as e: 并记录", fid))
        # except: pass 静默吞
        if re.search(r"except[^:]*:\s*pass\s*$", stripped):
            findings.append(_mk("pass-in-except", "warning", i, _trim(line),
                                "异常被 pass 静默吞没,问题无法暴露",
                                "至少 logging 记录", fid))
        # TODO/FIXME
        if re.search(r"\b(TODO|FIXME|XXX)\b", stripped):
            findings.append(_mk("todo-comment", "info", i, _trim(line),
                                "遗留 TODO/FIXME 待处理",
                                "评估并处理或记录到任务系统", fid))
    return findings


def scan_metrics(lines, lang):
    """函数级指标:圈复杂度近似、长函数。仅 Python/JS 粗略解析。"""
    metrics = {"per_function": [], "long_functions": [], "todos": []}
    if lang not in ("python", "javascript", "typescript", "java"):
        return metrics
    # 按 def/function 切分(Python:def ; JS/TS/Java:function/void/type )
    if lang == "python":
        pat = re.compile(r"^(async\s+)?def\s+([A-Za-z_]\w*)\s*\(")
    else:
        pat = re.compile(r"^\s*(export\s+)?(async\s+)?function\s+([A-Za-z_]\w*)")
    starts = []
    for i, line in enumerate(lines):
        if pat.match(line):
            starts.append(i)
    starts.append(len(lines))
    branch_re = re.compile(r"\b(if|elif|for|while|and|or|case|catch|except)\b|[\?]")
    for idx in range(len(starts) - 1):
        s = starts[idx]
        e = starts[idx + 1]
        body = lines[s:e]
        body_text = "\n".join(body)
        cc = len(branch_re.findall(body_text))
        name_m = pat.match(lines[s])
        name = name_m.group(2 if lang == "python" else 3) if name_m else "fn"
        metrics["per_function"].append({"name": name, "line": s + 1, "lines": e - s, "complexity": cc})
        if e - s > 50:
            metrics["long_functions"].append({"name": name, "line": s + 1, "lines": e - s})
    return metrics


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


# ---------- 主扫描 ----------

def cmd_scan(path, lang=None):
    text = read_code(path)
    if lang is None:
        lang = guess_lang(path, text)
    lines = text.splitlines()
    sec = scan_security(lines, lang)
    defects = scan_defects(lines, lang)
    metrics = scan_metrics(lines, lang)
    findings = sec + defects
    # 排序: critical > warning > info, 再按行号
    order = {"critical": 0, "warning": 1, "info": 2}
    findings.sort(key=lambda f: (order.get(f["severity"], 9), f["line"]))
    # 重新编号
    for i, f in enumerate(findings, start=1):
        f["id"] = i
    counts = {"critical": sum(1 for f in findings if f["severity"] == "critical"),
              "warning": sum(1 for f in findings if f["severity"] == "warning"),
              "info": sum(1 for f in findings if f["severity"] == "info")}
    func_count = len(metrics["per_function"])
    return {
        "summary": {
            "lang": lang, "lines": len(lines), "func_count": func_count,
            "counts": counts,
            "overall": "需整改" if counts["critical"] > 0 else ("合格" if counts["warning"] <= 2 else "合格-有警告"),
        },
        "findings": findings,
        "metrics": metrics,
    }


def main():
    if len(sys.argv) < 3:
        print(json.dumps({"error": "用法: python review.py scan <文件> [--lang 语言]"},
                         ensure_ascii=False))
        sys.exit(2)
    cmd = sys.argv[1]
    if cmd != "scan":
        print(json.dumps({"error": f"未知子命令: {cmd}(应为 scan)"}, ensure_ascii=False))
        sys.exit(2)
    path = sys.argv[2]
    lang = None
    if "--lang" in sys.argv:
        idx = sys.argv.index("--lang")
        lang = sys.argv[idx + 1] if idx + 1 < len(sys.argv) else None
    try:
        result = cmd_scan(path, lang)
    except FileNotFoundError as e:
        result = {"error": str(e)}
    except Exception as e:
        result = {"error": f"扫描失败: {type(e).__name__}: {e}"}
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
