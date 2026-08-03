#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
人岗匹配脚本自测。

功能: 用 samples 下的简历/JD 样例验证 match.py 的 parse/parse-jd/score 三子命令,
     确认要素抽取、技能匹配、年限比对、硬性判定、PII 脱敏正确且不崩溃。
创建日期: 2026-08-03

输入: samples/简历-后端开发.txt, samples/JD-Java后端.txt。
输出: 控制台打印每项断言; 全通过 exit 0,否则 exit 1。
"""

import sys
import os
import json
import subprocess

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SCRIPT = os.path.join(ROOT, "scripts", "match.py")
RESUME = os.path.join(ROOT, "samples", "简历-后端开发.txt")
JD = os.path.join(ROOT, "samples", "JD-Java后端.txt")
PY = sys.executable

PASS = 0
FAIL = 0


def run(cmd, *paths):
    args = [PY, SCRIPT, cmd] + list(paths)
    out = subprocess.run(args, capture_output=True, text=True, encoding="utf-8")
    if out.returncode != 0:
        print(f"[FAIL] 子命令 {cmd} 退出码 {out.returncode}: {out.stderr}")
        return None
    try:
        return json.loads(out.stdout)
    except json.JSONDecodeError:
        print(f"[FAIL] 子命令 {cmd} 输出非 JSON: {out.stdout[:200]}")
        return None


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"[PASS] {name}")
    else:
        FAIL += 1
        print(f"[FAIL] {name}  {detail}")


def main():
    print("=" * 60)
    print("resume-job-match 自测开始")
    print("=" * 60)

    # ---- parse 简历 ----
    r = run("parse", RESUME)
    if r:
        check("parse: 抽到姓名张伟", r["basic"]["name"] == "张伟", str(r["basic"]))
        check("parse: 手机已脱敏(含****)", r["basic"]["phone"] and "****" in r["basic"]["phone"],
              str(r["basic"]["phone"]))
        check("parse: 邮箱已脱敏(含***)", r["basic"]["email"] and "***" in r["basic"]["email"],
              str(r["basic"]["email"]))
        check("parse: 学历=本科", r["education_level"] == "本科", str(r["education_level"]))
        check("parse: 工作年限=5", r["work_years"] == 5, str(r["work_years"]))
        sk = r["skills"]
        check("parse: 命中 java", "java" in sk, str(sk))
        check("parse: 命中 spring boot", "spring boot" in sk, str(sk))
        check("parse: 命中 kubernetes(k8s归一)", "kubernetes" in sk, str(sk))
        check("parse: 命中 redis/mysql", "redis" in sk and "mysql" in sk, str(sk))
        check("parse: 证书含软考", "软考" in r["certs"], str(r["certs"]))
        check("parse: 抽到项目>=1", len(r["projects"]) >= 1, str(r["projects"]))

    # ---- parse-jd ----
    j = run("parse-jd", JD)
    if j:
        check("parse-jd: 岗位名含Java后端", j["title"] and "Java" in j["title"], str(j["title"]))
        check("parse-jd: 学历要求=本科", j["hard"]["edu"] == "本科", str(j["hard"]["edu"]))
        check("parse-jd: 年限要求=3", j["hard"]["years"] == 3, str(j["hard"]["years"]))
        check("parse-jd: 必备含java", "java" in j["hard"]["skills"], str(j["hard"]["skills"]))
        check("parse-jd: 必备含spring", "spring" in j["hard"]["skills"], str(j["hard"]["skills"]))
        check("parse-jd: 加分含docker/k8s", "docker" in j["plus"]["skills"] and "kubernetes" in j["plus"]["skills"],
              str(j["plus"]["skills"]))

    # ---- score ----
    s = run("score", RESUME, JD)
    if s:
        check("score: 必备技能全命中(无miss)", s["skill_hits"]["hard_miss"] == [],
              str(s["skill_hits"]["hard_miss"]))
        check("score: 硬性通过", s["pass_hard"] is True, str(s["pass_hard"]))
        check("score: 加分命中docker/k8s",
              "docker" in s["skill_hits"]["plus_hit"] and "kubernetes" in s["skill_hits"]["plus_hit"],
              str(s["skill_hits"]["plus_hit"]))
        check("score: 年限pass=True", s["year_match"]["pass"] is True, str(s["year_match"]))
        check("score: 学历pass=True", s["edu_match"]["pass"] is True, str(s["edu_match"]))
        check("score: 相关性项留空待AI补", s["machine_score"]["relevance"]["score"] is None)
        check("score: 给出初步分", isinstance(s["preliminary_score_pct"], (int, float)) and s["preliminary_score_pct"] > 0,
              str(s["preliminary_score_pct"]))

    # ---- PII 脱敏独立检查 ----
    sys.path.insert(0, os.path.join(ROOT, "scripts"))
    import match  # noqa
    check("mask: 手机脱敏", match.mask_phone("电话13812345678") == "电话138****5678",
          match.mask_phone("电话13812345678"))
    check("mask: 邮箱脱敏", "***" in match.mask_email("abc@example.com"), match.mask_email("abc@example.com"))

    # ---- 不匹配场景: 前端简历投Java后端(用一份伪造的不匹配文本) ----
    fe_resume = os.path.join(HERE, "_fe_tmp.txt")
    with open(fe_resume, "w", encoding="utf-8") as f:
        f.write("姓名:李四 手机:13900000000 邮箱:lisi@example.com\n前端工程师,2年经验,熟练vue/react/html/css,无java经验,大专学历")
    s2 = run("score", fe_resume, JD)
    if s2:
        check("不匹配: java在miss里", "java" in s2["skill_hits"]["hard_miss"], str(s2["skill_hits"]["hard_miss"]))
        check("不匹配: 硬性未通过", s2["pass_hard"] is False, str(s2["pass_hard"]))
    os.remove(fe_resume)

    # ---- 异常输入 ----
    err = run("parse", os.path.join(ROOT, "samples", "不存在.txt"))
    check("异常: 文件不存在返回error", err is not None and "error" in err, str(err))

    # ---- sanitize ----
    sval = match.sanitize_cell("a|b<c>&=d")
    check("sanitize: 转义", "\\|" in sval and "&lt;" in sval and "&amp;" in sval and "&amp;lt;" not in sval, sval)

    print("=" * 60)
    print(f"自测结束: 通过 {PASS} 项, 失败 {FAIL} 项")
    print("=" * 60)
    sys.exit(0 if FAIL == 0 else 1)


if __name__ == "__main__":
    main()
