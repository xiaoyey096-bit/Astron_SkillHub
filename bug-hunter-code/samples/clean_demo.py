"""订单查询服务(合规示例,无明显安全/缺陷问题)。"""
import os
import sqlite3
import subprocess
from pathlib import Path

API_KEY = os.environ.get("ORDER_API_KEY", "")


def query_orders(user_id, keyword):
    """参数化查询,避免 SQL 注入。"""
    with sqlite3.connect("orders.db") as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM orders WHERE user_id = ? AND name LIKE ?",
            (user_id, f"%{keyword}%"),
        )
        return cur.fetchall()


def run_report(report_name):
    """使用 shell=False + 参数列表,避免命令注入。"""
    if not report_name.isidentifier():
        raise ValueError("非法报表名")
    result = subprocess.run(
        ["generate-report", report_name], shell=False, capture_output=True, check=True
    )
    return result.stdout


def list_files(base_dir, rel_path):
    """校验路径在根目录内,避免路径穿越。"""
    root = Path(base_dir).resolve()
    target = (root / rel_path).resolve()
    if not str(target).startswith(str(root)):
        raise ValueError("非法路径")
    return sorted(p.name for p in target.iterdir())


def parse_config(value):
    """异常记录而非静默吞没。"""
    try:
        return int(value)
    except (TypeError, ValueError) as e:
        print(f"[warn] 配置解析失败: {e}")
        return None
