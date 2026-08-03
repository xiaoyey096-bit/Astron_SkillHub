# 讯飞 Skill 开发规范速查（基于官方《Skill 开发与提交指南》）

> 本文档浓缩自讯飞 SkillHub 官方《Skill 开发与提交指南》，作为开发任何 Skill 时的速查规范。
> **核心原则：`name` 一律用英文 slug（全小写+连字符），目录名与 `name` 一致。**

---

## 一、文件结构（最小必需 + 进阶）

### 最小必需
```
my-skill/
└── SKILL.md          # 唯一必需文件（主指令）
```

### 进阶（推荐）
```
my-skill/
├── SKILL.md          # 主指令（必需）
├── references/       # 长篇参考资料（SKILL.md 显式引用才加载，省 token）
│   └── spec.md
├── templates/        # 输出模板
│   └── output.md
├── examples/         # 输入输出示例
│   ├── input-1.md
│   └── output-1.md
├── scripts/          # 可执行脚本
│   └── helper.py
└── README.md         # 中文使用说明（非必需，建议有）
```

> 支撑文件**不会自动加载**到 AI 上下文，只在 SKILL.md 显式引用时才被读取。

---

## 二、SKILL.md 规范（最关键）

由两部分组成：**YAML frontmatter**（顶部 `---` 包围）+ **Markdown 正文**。

### frontmatter 字段

| 字段 | 必填 | 说明 |
|------|------|------|
| `name` | ✅ 是 | Skill 唯一标识，必须符合 slug 规则（见下），缺失会发布失败 |
| `description` | ✅ 是 | "一句话说明做什么+何时用"，AI 据此判断是否加载，缺失会发布失败 |
| `version` | ❌ 否 | 自定义版本号字符串，不填即空，平台不自动赋默认值 |
| 其他 | ❌ 否 | 任何额外字段不报错，但平台**不解析、不展示**（只对其他客户端生效） |

### ① name 字段规则（必须全过）

| 规则 | 要求 | 正例 / 反例 |
|------|------|------------|
| 长度 | 2-64 字符 | ✅ `my-skill` ❌ `a` |
| 字符集 | Unicode 字母、数字、`-` | ✅ `data-cleaner-v2` |
| **大小写** | **必须全小写** | ❌ `MySkill` |
| 起止字符 | 首尾不能是 `-` | ❌ `-my-skill`、`my-skill-` |
| 连续连字符 | 不允许 `--` | ❌ `my--skill` |
| 保留字 | 禁用：`admin` `api` `dashboard` `search` `auth` `me` `global` `system` `static` `assets` `health` | ❌ `name: api` |
| **推荐风格** | **全小写字母 + 连字符** | ✅ `gongwen-spec-audit`、`ecom-competitor-benchmark` |

> **本项目约定：name 一律用英文 slug**（如 `gongwen-spec-audit`）。虽然官方允许中文（如 `中译英-translator`），但英文 slug 最不易触发规则边界、最通用。中文辨识度放 SKILL.md 标题和 description。

### ② description 字段规则

- **AI 决定是否加载本 Skill 的依据**，当"销售文案"来写。
- **口诀：动作 + 触发关键词 + 关键约束**。
- 好坏对比：

| 写法 | 效果 |
|------|------|
| `翻译相关` | ❌ 太泛，AI 不知道何时加载 |
| `做翻译` | ❌ 缺触发关键词 |
| `中译英翻译。用户说"翻译""translate"或要求把中文转成英文时使用，保留专业术语和语气` | ✅ 动作+触发词+行为约束 |

---

## 三、SKILL.md 标准模板（直接套用）

```markdown
---
name: <英文-slug-名>             # 全小写+连字符,2-64字符,非保留字
description: <动作+触发关键词+关键约束>  # 一句话,AI据此判断加载
---

# <中文技能名>（<英文-slug-名>）

## 何时加载（触发条件/适用场景）
<列出用户说什么时加载本 Skill,以及不应加载的场景(避免跨场景误触发)>

## 标准工作流程（SOP）
<分步骤说明执行流程,含输入/处理/输出>

## 输入输出约定
<输入是什么(粘贴文本/文件路径),输出是什么格式>

## 不应该做什么（能力边界）
<不编造什么、不联网、不做哪些超范围的事>
```

> 正文建议包含：触发条件/适用场景、操作步骤、输入/输出示例、已知限制。

---

## 四、打包提交规范

### ZIP 要求

| 规则 | 限制 |
|------|------|
| 总包大小 | ≤ **100 MB** |
| 单文件大小 | ≤ **10 MB** |
| 文件总数 | ≤ **500 个** |
| 必须包含 | `SKILL.md`（位于根目录或唯一子目录） |
| 路径分隔符 | `/`（Windows `\` 会自动转换） |
| **不允许** | 绝对路径、`..` 越级、Windows 盘符（`C:`）、空路径 |

### 两种打包方式都接受

- **方式 A**：ZIP 内顶层直接是 `SKILL.md`
- **方式 B**：ZIP 内有一层包名目录 `my-skill/SKILL.md`（**推荐**，提交时填的作品名要和 name 一致）

> 平台最终存储时会统一去掉外层目录。

### 打包命令
```bash
zip -r my-skill.zip my-skill    # 目录名 = name slug
```

---

## 五、文件类型白名单（只这些扩展名会被保留）

| 类型 | 扩展名 |
|------|--------|
| 文档 | `.md` `.txt` `.json` `.yaml` `.yml` `.html` `.css` `.csv` `.pdf` |
| 配置 | `.toml` `.xml` `.xsd` `.xsl` `.dtd` `.ini` `.cfg` `.env` |
| 脚本/源码 | `.js` `.cjs` `.mjs` `.ts` `.py` `.sh` `.rb` `.go` `.rs` `.java` `.kt` `.lua` `.sql` `.r` `.bat` `.ps1` `.zsh` `.bash` |
| 图片 | `.png` `.jpg` `.jpeg` `.svg` `.gif` `.webp` `.ico` |
| Office | `.doc` `.xls` `.ppt` `.docx` `.xlsx` `.pptx` |

### ❌ 不允许的文件类型
- 压缩包：`.zip`（禁止套 zip）`.tar` `.gz` `.7z` `.rar`
- 可执行：`.exe` `.dll` `.so` `.dylib` `.bin`
- 视频/音频：`.mp4` `.mp3` `.wav` `.avi`
- 数据库：`.sqlite` `.db`
- 临时文件：`.bak` `.tmp` `.swp`

---

## 六、凭证扫描（发布会扫描，疑似真实凭证会警告影响审核）

### 会被识别的密钥模式（避免硬编码）
| 类型 | 模式 |
|------|------|
| AWS Access Key | `AKIA` 开头 + 16 位大写字母数字 |
| GitHub Token | `ghp_` 开头 + ≥20 位字母数字 |
| OpenAI/通用 API Key | `sk-` 开头 + ≥20 位字母数字 |
| 通用密钥赋值 | `api_key`/`access_key`/`secret`/`password`/`token` 后跟 `:` 或 `=` 加 ≥12 位值 |

### ✅ 自动豁免的占位符
含 `your`、`example`、`sample`、`placeholder`、`changeme`、`replace`、`dummy`、`mock`、`test`、`fake`、`todo`、`xxx`、`redacted` 之一，或全是 `x`/`X`/`*`/`-`。

> **凭证用占位符（如 `your-api-key`）或环境变量引导，绝不硬编码真实密钥。**

---

## 七、内容校验（附加）

- 文本类文件须为合法 **UTF-8 编码**，不允许 NUL 字节。
- 图片有魔数校验（PNG `89 50 4E 47`、JPEG `FF D8 FF`、GIF `GIF8`、WebP `RIFF...WEBP`、PDF `%PDF`、ICO `00 00 01 00`、SVG 须含 `<svg`）。
- **改扩展名伪装（`.txt` → `.png`）会被识破并拒绝**。

---

## 八、评审机制

- 通过审核 → 进入"Skill 热度榜"，**热度 = 下载量 + 收藏量**，是评审重要依据。
- 官方有**刷量检测**：禁止用脚本批量调用下载接口、同机多无痕窗口刷量。
- 鼓励在社媒/私域正常宣传，正常传播不触发风控。

---

## 九、上架前自查清单（提交前必过）

### 平台与合规（一票否决）
- [ ] 全量搜索无境外模型/平台引用（openai/claude/gemini/anthropic/gpt/googleapis/twitter/facebook/youtube/telegram）
- [ ] 无境外社交平台引导、无境外 API 端点、无境外平台资源（Google Fonts/Maps）
- [ ] 无境外 Skill 平台入口（ClawHub/SkillsMP/Skills.sh/MCP Market）
- [ ] 无政治敏感、破解/激活码、VPN/翻墙、印章透明背景等滥用功能

### 凭据与密钥
- [ ] 无真实 API Key/Token/Secret（用占位符或环境变量）

### 代码安全
- [ ] 无命令注入（shell=True/os.system/eval/exec）
- [ ] 无 SSRF（任意 URL 无过滤）、无 SSL 禁用（CERT_NONE/check_hostname=False）
- [ ] 文件路径有净化（过滤 `..`/非法字符）、ZIP 解压有 zip-slip 防护

### 数据隐私与注入
- [ ] PII 脱敏 + 隐私声明（若处理个人信息）
- [ ] Markdown/CSV/HTML/SVG 输出已转义（`|`/`<>&`/公式前缀`=+-@`/链接`[]()`/`javascript:`）

### 依赖与质量
- [ ] 第三方库版本锁定、标准库不误入 requirements
- [ ] 无 `__pycache__`/`.pyc`/死代码/绝对路径残留

### 规范符合
- [ ] `name` 满足全部 slug 规则（全小写/2-64/字母数字连字符/首尾非`-`/无`--`/非保留字）
- [ ] frontmatter 仅 `name`+`description`（+可选`version`）
- [ ] ZIP 内 SKILL.md 在根目录或唯一子目录，无绝对路径/越级/盘符
- [ ] 体积≤100MB、单文件≤10MB、文件数≤500、文件类型在白名单内

---

## 十、Quickstart 官方示例（参考）

```markdown
---
name: my-first-skill
description: 帮助用户把一段中文翻译成英文。用户提到 "翻译"、"translate"、"译成英文" 时调用。
---

# 中文翻英文

## 触发条件
用户提到以下任意场景时，使用本 Skill：
- 给一段中文，要求翻译成英文
- 出现关键词 "translate"、"翻译"、"译成英文"

## 操作步骤
1. 接收用户的原文（中文）
2. 翻译时保留原文的语气与专业术语
3. 输出格式：
   - **原文**：<中文>
   - **译文**：<英文>

## 示例
输入：今天天气真好。
输出：
- **原文**：今天天气真好。
- **译文**：The weather is really nice today.
```

---

## 附：本项目命名约定

| 项 | 约定 | 示例 |
|----|------|------|
| `name`（frontmatter） | 英文 slug | `gongwen-spec-audit` |
| 目录名 | = name slug | `gongwen-spec-audit/` |
| ZIP 名 | = name slug + `.zip` | `gongwen-spec-audit.zip` |
| 中文技能名 | 放 SKILL.md 标题 + description | 公文智能处理助手 |
| 提交作品名 | 与 name 一致 | gongwen-spec-audit |
