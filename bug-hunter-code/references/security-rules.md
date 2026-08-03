# 安全漏洞扫描规则库（security-rules）

> 供 `scripts/review.py` 做确定性安全扫描。每条规则含：规则名、适用语言、命中模式、风险等级、修复方向。
> 命中即按规则定义报，由 AI 在报告中补上下文说明与修复示例。

## 一、命令注入（🔴严重）

| 规则 | 适用语言 | 命中模式 | 修复方向 |
|------|---------|---------|---------|
| shell-true | Python | `shell=True` 且参数含变量/拼接 | 改 `shell=False` + 参数列表 |
| os-system | Python | `os.system(` 且含字符串拼接/格式化 | 改 `subprocess.run([..], shell=False)` |
| os-popen | Python | `os.popen(` 含用户输入 | 同上，改 subprocess |
| eval-exec | Python/JS | `eval(` / `exec(` 处理非字面量 | 禁用，改安全解析 |
| child-process-exec | Node.js | `child_process.exec(` 含拼接 | 改 `execFileSync(cmd,[args])` |

## 二、SQL 注入（🔴严重）

| 规则 | 适用语言 | 命中模式 | 修复方向 |
|------|---------|---------|---------|
| sql-concat | 通用 | `SELECT/INSERT/UPDATE/DELETE` 字符串与 `%`/`+`/`f"`/`.format` 拼接变量 | 参数化查询（占位符） |
| sql-format | Python | `cursor.execute("...%s..." % var)` 或 `f"select ...{var}"` | `execute(sql, (var,))` |

## 三、硬编码密钥（🔴严重）

| 规则 | 适用语言 | 命中模式 | 修复方向 |
|------|---------|---------|---------|
| api-key-hardcode | 通用 | `sk-` + ≥20 位字母数字（非占位符） | 改环境变量 |
| password-assign | 通用 | `password=`/`api_key=`/`secret=`/`token=` 后跟 ≥12 位字面量值（非占位符/非空） | 改环境变量/配置 |
| aws-key | 通用 | `AKIA` + 16 位大写字母数字 | 删除，改环境变量 |

> **占位符豁免**：值含 `your/example/sample/placeholder/changeme/replace/dummy/mock/test/fake/xxx/redacted` 或全 `x/*/–` 的不报。

## 四、路径穿越（🟡警告～🔴严重）

| 规则 | 适用语言 | 命中模式 | 修复方向 |
|------|---------|---------|---------|
| path-userinput | 通用 | `open(` / `read_file(` 参数含用户输入变量且无校验 | 过滤 `..`/`/`、白名单 |
| zip-slip | Python | `zipfile` 解压时 `extract(path)` 拼接成员名无校验 | 校验解压目标在根目录内 |

## 五、不安全反序列化（🔴严重）

| 规则 | 适用语言 | 命中模式 | 修复方向 |
|------|---------|---------|---------|
| pickle-load | Python | `pickle.loads(` / `pickle.load(` 处理外部数据 | 改 JSON 等安全格式 |
| yaml-unsafe-load | Python | `yaml.load(` 不带 `Loader=SafeLoader` | 改 `yaml.safe_load` |

## 六、SSL/传输安全（🟡警告）

| 规则 | 适用语言 | 命中模式 | 修复方向 |
|------|---------|---------|---------|
| ssl-verify-false | Python | `verify=False` / `CERT_NONE` / `check_hostname=False` | 删除，启用验证 |
| tls-reject | Node.js | `rejectUnauthorized:false` / `NODE_TLS_REJECT_UNAUTHORIZED='0'` | 删除 |

## 七、SSRF（🟡警告）

| 规则 | 适用语言 | 命中模式 | 修复方向 |
|------|---------|---------|---------|
| ssrf-no-filter | 通用 | `requests.get(` 用户传 URL 且无内网地址过滤/协议限制 | 白名单校验、禁内网 |

> 本规则库聚焦赛题主场景（Python/JS/Java 通用模式）。语言特定规则可扩展。
