# 缺陷与坏味道规则库（defect-rules）

> 供 `scripts/review.py` 做确定性缺陷/坏味道扫描。命中按规则报，AI 补语义说明。

## 一、资源未释放（🟡警告）

| 规则 | 适用语言 | 命中模式 | 修复方向 |
|------|---------|---------|---------|
| file-no-close | Python | `open(` 但未在 `with` 块内、且无对应 `close()` | 改 `with open(..) as f:` |
| conn-no-close | 通用 | 建立 socket/数据库连接但无 close/with | try-finally 或上下文管理器 |

## 二、异常处理（🟡警告）

| 规则 | 适用语言 | 命中模式 | 修复方向 |
|------|---------|---------|---------|
| bare-except | Python | `except:` 裸捕获（无异常类型） | 改 `except Exception as e:` 并记录 |
| pass-in-except | Python | `except ...: pass` 静默吞异常 | 至少 logging，不要静默 |
| broad-except | Java | `catch (Exception e)` 且方法体空/仅 print | 缩窄异常类型、记录日志 |

## 三、空值/未初始化（🟡警告，语义依赖 AI）

| 规则 | 适用语言 | 命中模式 | 修复方向 |
|------|---------|---------|---------|
| none-use | 通用 | 变量可能为 None/未赋值即使用（AI 结合上下文判） | 加空值检查 |
| unchecked-return | 通用 | 函数返回值未检查即继续使用（如 dict.get） | 检查 None |

## 四、坏味道（🟢建议）

| 规则 | 适用语言 | 命中模式 | 修复方向 |
|------|---------|---------|---------|
| long-function | 通用 | 函数体 >50 行 | 拆分小函数 |
| high-complexity | 通用 | 圈复杂度高（if/for/while/and/or/case 分支数 >10） | 拆分/提前返回 |
| magic-number | 通用 | 代码中出现未命名的字面量常量 | 提取为命名常量 |
| duplicate-block | 通用 | 连续 ≥6 行重复代码块 | 提取公共函数 |
| todo-comment | 通用 | `TODO`/`FIXME`/`XXX` 注释 | 列出待办，提醒处理 |

## 五、命名/可读性（🟢建议，语义依赖 AI）

- 变量名过短/无意义（如 `a`/`x1`/`temp`）→ 建议语义化命名；
- 函数名不能表达意图 → 建议改名；
- 缺少关键逻辑注释 → 建议补充。

> 复杂度计算（粗略）：统计函数体内 `if/elif/for/while/and/or/case/?/catch` 出现次数作为圈复杂度近似值，>10 标高复杂度。
