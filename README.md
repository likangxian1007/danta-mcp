# 旦挞 MCP · DanTa MCP

[English](./README.en.md) | **中文**

让 AI 自动检索**复旦树洞**和**旦克课程评价**的 MCP 服务器。校外可用。

树洞是复旦学生的匿名社区——生活、情感、就业、心理、转专业、二手交易，什么都聊。
这个工具让 AI 帮你把这些真实经验搜出来、读完、汇总，而不是自己一页页翻。

```
你：帮我查一下高等微积分Ⅰ这门课怎么样

AI：（自动调用 search_courses → get_course_reviews）
    找到「高等微积分Ⅰ」(MATH20021)，相辉学堂，5 学分，3 条评价。
    教师严金海 + 王嬴（习题课）
    综合评分 ★★★★★ / ★★★★☆
    - 给分：两位评价者最终都拿了 A，但都提到"课下要花很多时间"
    - 严老师：PPT 有用、往年卷会分享、题型固定不偏；但上课爱扯题外话
    - 王嬴老师：口碑极好，答疑响应快，改作业细致
    - 难度：期中偏难，秋季学期后考试强度有下降
```

---

## 目录

- [能干什么](#能干什么)
- [快速开始](#快速开始)
- [工具说明](#工具说明)
- [工作原理](#工作原理)
- [安全设计](#安全设计)
- [排障](#排障)
- [已知限制](#已知限制)
- [许可证](#许可证)

---

## 能干什么

配好之后直接用自然语言问，AI 会自动调工具：

| 场景 | 直接说 |
|---|---|
| 🍜 生活 | 「哪个食堂好吃」「宿舍空调怎么修」「校医院靠谱吗」 |
| 💔 情感 | 「树洞里异地恋都怎么处理的」「大家怎么看待校园恋爱」 |
| 💼 就业 | 「最近有什么实习内推」「信院就业前景怎么样」 |
| 🧠 心理 | 「大家怎么应对开学焦虑」「学校心理咨询好约吗」 |
| 🔄 学业 | 「转专业难不难，过来人怎么说」「保研经验」 |
| 👥 交友 | 「怎么找搭子」「社团值得进吗」 |
| 💰 交易 | 「二手电动车行情」「合租信息」 |
| 📚 选课 | 「高等微积分Ⅰ值得选吗」「对比这三门通识课」 |

数据来源：**复旦树洞**（实时匿名讨论，23000+ 话题标签）+ **旦克课程评价库**（结构化评分 + 学生长评）。

---

## 快速开始

### 前置要求

- Python 3.10+
- 一个复旦 UIS 账号（学号 + 密码）
- 一个旦挞/树洞账号（邮箱 + 密码，在 [旦挞 App](https://danxi.fduhole.com) 里注册）
- 一个支持 MCP 的客户端（Hermes / Claude Desktop / Cline 等）

### 1. 安装

```bash
git clone <你的仓库地址> danta-mcp
cd danta-mcp

# Windows
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt

# macOS / Linux
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

### 2. 配置凭据

```bash
# Windows
.venv\Scripts\python setup_credentials.py

# macOS / Linux
.venv/bin/python setup_credentials.py
```

会依次问你两组账号（密码输入时不回显）：

```
— 复旦 UIS 统一身份认证（学号 + 密码）
  用户名: 20307130001
  密码（不回显）:
  ✅ 已保存

— 旦挞/树洞账号（邮箱 + 密码）
  用户名: 20307130001@m.fudan.edu.cn
  密码（不回显）:
  ✅ 已保存
```

存储位置：
- **Windows** → 凭据管理器（DPAPI 加密，绑定你的 Windows 账户）
- **macOS/Linux** → 系统钥匙串（需 `pip install keyring`）
- **任何平台** → 也可用环境变量 `DANTA_UIS_USER` / `DANTA_UIS_PASS` / `DANTA_HOLE_USER` / `DANTA_HOLE_PASS`

验证：

```bash
.venv/Scripts/python setup_credentials.py --check
```

### 3. 自检

```bash
.venv/Scripts/python -E verify_mcp.py
```

应看到：

```
✅ handshake OK — 10 tools registered:
   • search_courses
   ...
✅ 连接正常
  WebVPN: 已建立会话
  用户 ID: 51359
✅ all checks passed
```

### 4. 接入 MCP 客户端

在客户端配置里加（**注意 `-E` 参数不能少**，见[排障](#排障)）：

```json
{
  "mcpServers": {
    "danta": {
      "command": "/绝对路径/danta-mcp/.venv/Scripts/python.exe",
      "args": ["-E", "/绝对路径/danta-mcp/run_server.py"],
      "cwd": "/绝对路径/danta-mcp"
    }
  }
}
```

Hermes 用户写在 `config.yaml` 的 `mcp_servers:` 下（YAML 格式，字段同上）。

重启客户端即可。

---

## 工具说明

### 树洞检索（通用，什么话题都能搜）

#### `search_holes(keyword, limit=15, accurate=False, within_days=0)`
全站搜索树洞内容。**这是最常用的工具。**

```
search_holes("食堂")                      # 模糊搜索
search_holes("转专业", accurate=True)      # 精确匹配，关键词必须完整出现
search_holes("实习", within_days=14)       # 只看最近两周
```

- `accurate=True` — 精确匹配，适合专有名词、课程代码、人名
- `within_days=N` — 只看最近 N 天，适合找时效性内容（实习招聘、最新政策）

#### `get_hole(hole_id, limit=40)`
读某个树洞的全部楼层。

**树洞的价值常在回复里** —— 楼主提问，楼里的人给经验。搜到感兴趣的洞一定要读全文。

#### `browse_by_tag(tag, limit=15)`
按话题标签浏览最新树洞。比关键词搜索更适合"逛"某个话题。

常用标签：`提问` `求助` `生活` `学习` `恋爱` `情感` `吐槽` `emo` `交友`
`选课` `转专业` `保研` `期末考试` `出分` `二手交易` `找搭子` `军训` `家教`

#### `list_hot_tags(limit=40, keyword="")`
列出最热门的话题标签（按热度排序），可过滤。

```
list_hot_tags()                  # 看树洞上大家都在聊什么
list_hot_tags(keyword="实习")     # 找所有和实习相关的标签
```

树洞共有 23000+ 标签，热度前几名：提问(18万) 求助氵(9.5万) 生活(7.4万)
学习(6万) 恋爱(3.7万) 吐槽(2.3万) emo(1.8万)。

#### `browse_division(division_id, limit=15)` / `list_divisions()`
按板块浏览：

| ID | 板块 | 说明 |
|---|---|---|
| **1** | **茶楼** | **主板，什么都聊——日常首选** |
| 2 | 圆桌 | 深入讨论 |
| 3 | 评教 | 课程/教师评价 |
| 4 | 站务 | 论坛管理 |
| 5 | 交易 | 二手/合租/代购 |

### 课程评价（旦克）

#### `search_courses(keyword, limit=10)`
搜课程。keyword 可以是课程名、课程代码、关键词。

```
search_courses("微积分")
→ [1136] 微积分（上）(MATH120012) 基础医学院 | 评价数: 0
  [8911] 高等微积分Ⅰ (MATH20021) 相辉学堂 | 评价数: 3
```

**先看评价数**，为 0 的课没有参考价值。

#### `get_course_reviews(course_group_id, max_reviews=12)`
看某门课的完整评价，按「教师 + 学期」分组。

返回内容包含：
- 四维评分：**综合 / 内容 / 工作量 / 考核**（1-5 星）
- `remark` 推荐指数、点赞数
- 评价正文（通常含给分情况、考试难度、作业量、助教情况）

### 树洞

#### `search_holes(keyword, limit=15)`
全站搜索树洞内容。适合找老师风评、选课经验、真实吐槽。

#### `get_hole(hole_id, limit=40)`
读某个树洞的全部楼层。

#### `list_divisions()` / `browse_division(division_id, limit=15)`
板块浏览。板块 ID：

| ID | 板块 | 说明 |
|---|---|---|
| 1 | 茶楼 | 主论坛 |
| 2 | 圆桌 | 畅所欲言 |
| **3** | **评教** | **选课季重点看这个** |
| 4 | 站务 | 论坛管理 |
| 5 | 交易 | 非商业广告 |

### 排障

#### `build_citation_report(title, queries, summary_markdown="", per_query=6)`
把检索结果生成一份**带完整出处的 HTML 引证报告**，保存到桌面，浏览器打开即可。

每条引用保留：洞号（可点击溯源）、楼层、匿名昵称、时间、点赞数、**原文照登**。
适合需要人工核对结论的场景 —— 你可以逐条检查 AI 有没有过度解读。

```
build_citation_report(
  title="复旦留学生宿舍 · 快递地址怎么填",
  queries="北区驿站::北区 菜鸟驿站|顺丰京东::顺丰 京东 本部|hole:692300::地址怎么写",
  summary_markdown="<p>结论写在这里</p>"
)
```

`queries` 用 `|` 分隔多个来源分组，每组格式 `小节标题::关键词`；
也支持 `hole:洞号` 直接引用整个树洞的所有楼层。

报告特性：响应式布局、自动适配深色模式、内容全部 HTML 转义（防注入）。

#### `check_connection()`
检查 WebVPN 会话、token、账号状态。出问题时先跑这个。

---

## 工作原理

### 为什么需要这一层

复旦树洞的 API 全部部署在校内：

```
forum.fduhole.com → 10.107.13.152   ← 校内私有地址
auth.fduhole.com  → 10.107.13.152
danke.fduhole.com → 10.107.13.152
```

校外**物理上无法直连**。本项目复刻了[旦挞官方客户端](https://github.com/DanXi-Dev/DanXi)的 WebVPN 方案。

### 完整链路

```
1. 读取凭据（系统钥匙串 / 环境变量）
        ↓
2. UIS 登录 id.fudan.edu.cn
   getJsPublicKey → RSA-PKCS1 加密密码 → authExecute → loginToken
        ↓
3. authnEngine → CAS ticket (ST-xxxxx)
        ↓
4. 兑换 ticket → 拿到 WebVPN 会话 cookie
        ↓
5. API 域名 AES-CFB 加密改写
   https://auth.fduhole.com/api/login
   → https://webvpn.fudan.edu.cn/https/7772647670...c38/api/login
        ↓
6. 树洞账号换 JWT → 之后所有请求带 Bearer
```

第 5 步的加密：AES-CFB，key = iv = `wrdvpnisthebest!`，主机名按**字符数**（非字节数）补齐到 16 的倍数，输出 `iv_hex + 密文hex[:2n]`。

> 自检小技巧：`auth.fduhole.com` 加密结果恒为
> `77726476706e69737468656265737421f1e2559469366c45760785a9d6562c38`，
> 前 32 位正是 `wrdvpnisthebest!` 的 hex。对不上说明实现有问题。

### 缓存

会话和 token 缓存在 `~/.danta-mcp/`：
- `cookies.json` — WebVPN 会话，6 小时后视为过期
- `token.json` — 树洞 JWT，20 天

正常使用**不会反复登录**。

### 校内直连

报到后连校园网 / eduroam，直连即可通，WebVPN 这层自动变成透明兜底，代码不用改。

---

## 安全设计

### 密码不落盘明文

存在系统级凭据库，代码只读不写副本。仓库里也没有任何凭据（见 `.gitignore`）。

### UIS 登录单次尝试，失败即停

**这是最重要的一条设计。**

复旦 UIS 对连续登录失败会触发验证码，一旦触发，必须手动打开浏览器登录一次才能解除。所以：

```python
# authExecute 明确 tries=1，绝不重试
r = self._req("POST", ".../authExecute", tries=1, json={...})
```

检测到 `message` 含「验证码」时**立即抛错并提示手动登录**，不会自动重试轰炸。

网络层重试（`tries=3`）只作用于 WebVPN 的**不稳定连接**，不作用于登录尝试。

### 缓存文件权限

`~/.danta-mcp/` 下的文件权限设为 `600`（仅所有者可读写）。

### 只读

本项目**只提供读取工具**，不提供发帖、回复、投票等写操作。AI 不会替你在树洞发言。

---

## 排障

### `No module named 'mcp.server.fastmcp'`

MCP SDK 2.x 把 `FastMCP` 改名为 `MCPServer`。`server.py` 已做双版本兼容，如果仍报错，说明 venv 被外部 `PYTHONPATH` 污染了 → 见下条。

### 工具在客户端里不出现 / 服务器启动即退出

**九成是 `PYTHONPATH` 污染。** 某些 MCP 宿主会把自己的 `site-packages` 注入子进程环境，盖掉本项目 venv 里的包。

解法：配置里必须用 `-E`（启动时忽略环境变量）：

```json
"args": ["-E", "/path/to/run_server.py"]
```

⚠️ 在代码里改 `sys.path` **是无效的** —— `sys.path` 在解释器启动时就由 `PYTHONPATH` 定型了。

### `❌ UIS 触发了验证码`

用浏览器打开 https://id.fudan.edu.cn 手动登录一次即可解除。

**不要反复重试**，会加重锁定。

### `login returned non-JSON`

WebVPN 会话过期，被弹回登录页。代码会自动重建会话重试一次。如果仍失败：

```bash
rm -rf ~/.danta-mcp   # 清缓存重新登录
```

### `IDP did not return a login context`

WebVPN 不稳（它的根路径 `/` 经常超时）。稍等重试即可。

### 改了 UIS 密码之后

```bash
.venv/Scripts/python setup_credentials.py
```

重新录入即可。

---

## 已知限制

- **依赖复旦认证系统的当前实现**。学校升级认证流程后可能失效，需跟进 [DanXi 上游](https://github.com/DanXi-Dev/DanXi) 的改动。
- **不支持双因素认证（2FA）**。如果你的账号开了增强认证，会抛 `EnhancedAuthenticationRequiredException`。
- **WebVPN 本身不稳定**，超时是常态，代码已加重试但无法完全消除。
- **课评数据取决于有没有人写**。冷门课可能一条评价都没有。
- 仅在 Windows 上完整测试过；macOS/Linux 的钥匙串路径写了但未实测。

---

## 联系

问题、建议或 bug 反馈：likangxian1007@gmail.com
或在 [Issues](https://github.com/likangxian1007/danta-mcp/issues) 提出。

---

## 许可证

**GPL-3.0** — 详见 [LICENSE](./LICENSE)。

本项目的 WebVPN 加密方案与 UIS 登录流程衍生自 [DanXi-Dev/DanXi](https://github.com/DanXi-Dev/DanXi)（GPL-3.0）。依据 GPL 传染性条款，本项目必须以相同许可证发布。

---

## 免责声明

本工具仅用于访问你**本人有权访问**的校内资源，等价于你手动登录网页所能看到的内容。

请遵守复旦大学网络使用规定和树洞社区公约。使用者对自己的行为负责。
