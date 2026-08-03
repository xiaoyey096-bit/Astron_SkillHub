"""订单查询服务(故意含多处安全/缺陷问题,供 bug-hunter-code 测试)。"""
import os
import pickle
import sqlite3
import subprocess


API_KEY = "your-key"
DB_PASSWORD = "your-pwd"


def query_orders(user_id, keyword):
    conn = sqlite3.connect("orders.db")
    cur = conn.cursor()
    sql = "SELECT * FROM orders WHERE user_id = %s AND name LIKE '%%%s%%'" % (user_id, keyword)
    cur.execute(sql)
    rows = cur.fetchall()
    return rows


def run_report(cmd):
    os.system("generate-report " + cmd)
    f = open("temp_report.txt", "w")
    f.write("done")
    return "ok"


def list_files(path):
    result = subprocess.run("ls -l " + path, shell=True, capture_output=True)
    return result.stdout


def load_session(data):
    session = pickle.loads(data)
    return session


def parse_config(value):
    try:
        return int(value)
    except:
        pass
    return None


def fetch_url(url):
    import requests
    resp = requests.get(url, verify=False)
    return resp.text
