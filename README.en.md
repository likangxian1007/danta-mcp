# DanTa MCP · 旦挞 MCP

**English** | [中文](./README.md)

An MCP server that lets an AI agent search **Fudan University's Tree Hole forum (树洞)** and **DanKe course reviews (旦克)** — including from off campus.

Built for course selection: instead of paging through reviews by hand, just ask your AI "is this course worth taking?" and let it search, read, and summarize.

```
You: What's 高等微积分Ⅰ (Advanced Calculus I) like?

AI: (auto-calls search_courses → get_course_reviews)
    Found 高等微积分Ⅰ (MATH20021), Xianghui Academy, 5 credits, 3 reviews.
    Instructors: Yan Jinhai + Wang Ying (recitation)
    Overall ★★★★★ / ★★★★☆
    - Grading: both reviewers ended with an A, but both note heavy out-of-class time
    - Prof. Yan: useful slides, shares past exams, predictable question types;
      tends to digress in lecture
    - Prof. Wang: excellent reputation, responsive to questions, detailed grading
    - Difficulty: midterm on the harder side; exam intensity eased in the fall term
```

---

## Contents

- [What it does](#what-it-does)
- [Quick start](#quick-start)
- [Tools](#tools)
- [How it works](#how-it-works)
- [Security design](#security-design)
- [Troubleshooting](#troubleshooting)
- [Known limitations](#known-limitations)
- [License](#license)

---

## What it does

Ask in natural language; the AI picks the tools.

| Goal | Just say |
|---|---|
| Research a course | "Is 高等微积分Ⅰ worth taking?" |
| Compare courses | "Compare the reviews for these three gen-ed courses" |
| Check an instructor | "Search the tree hole for opinions on Prof. Yan Jinhai" |
| Find selection tips | "What do people say about picking PE classes?" |
| Read a full thread | "Read all replies in hole #697119" |

Data comes from **DanKe** (structured ratings + long-form student reviews) and the **Fudan Tree Hole** (live discussion).

---

## Quick start

### Requirements

- Python 3.10+
- A Fudan UIS account (student ID + password)
- A DanTa / Tree Hole account (register in the [DanXi app](https://danxi.fduhole.com))
- An MCP-capable client (Hermes / Claude Desktop / Cline / …)

### 1. Install

```bash
git clone <your-repo-url> danta-mcp
cd danta-mcp

# Windows
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt

# macOS / Linux
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

### 2. Configure credentials

```bash
# Windows
.venv\Scripts\python setup_credentials.py

# macOS / Linux
.venv/bin/python setup_credentials.py
```

You'll be prompted for two accounts (passwords are not echoed):

```
— Fudan UIS (student ID + password)
  Username: 20307130001
  Password (hidden):
  ✅ saved

— DanTa / Tree Hole account (email + password)
  Username: 20307130001@m.fudan.edu.cn
  Password (hidden):
  ✅ saved
```

Storage backend:
- **Windows** → Credential Manager (DPAPI, bound to your Windows account)
- **macOS/Linux** → system keyring (requires `pip install keyring`)
- **Any platform** → environment variables `DANTA_UIS_USER` / `DANTA_UIS_PASS` / `DANTA_HOLE_USER` / `DANTA_HOLE_PASS`

Verify:

```bash
.venv/Scripts/python setup_credentials.py --check
```

### 3. Self-test

```bash
.venv/Scripts/python -E verify_mcp.py
```

Expected:

```
✅ handshake OK — 7 tools registered:
   • search_courses
   ...
✅ Connection OK
  WebVPN: session established
  User ID: 51359
✅ all checks passed
```

### 4. Register with your MCP client

Add this to your client config (**the `-E` flag is required** — see [Troubleshooting](#troubleshooting)):

```json
{
  "mcpServers": {
    "danta": {
      "command": "/abs/path/danta-mcp/.venv/Scripts/python.exe",
      "args": ["-E", "/abs/path/danta-mcp/run_server.py"],
      "cwd": "/abs/path/danta-mcp"
    }
  }
}
```

Hermes users: put the same fields under `mcp_servers:` in `config.yaml` (YAML syntax).

Restart the client.

---

## Tools

### Course reviews (DanKe)

#### `search_courses(keyword, limit=10)`
Search courses by name, course code, or keyword.

```
search_courses("微积分")
→ [1136] 微积分（上）(MATH120012) | reviews: 0
  [8911] 高等微积分Ⅰ (MATH20021)  | reviews: 3
```

**Check the review count first** — a course with 0 reviews tells you nothing.

#### `get_course_reviews(course_group_id, max_reviews=12)`
Full reviews for one course, grouped by instructor + term.

Includes:
- Four rating axes: **overall / content / workload / assessment** (1–5 stars)
- `remark` recommendation score and upvotes
- Review body (usually covers grading, exam difficulty, homework load, TAs)

### Tree Hole

#### `search_holes(keyword, limit=15)`
Full-text search across the forum. Good for instructor reputation and honest complaints.

#### `get_hole(hole_id, limit=40)`
Read every floor of a thread.

#### `list_divisions()` / `browse_division(division_id, limit=15)`
Browse by division:

| ID | Division | Notes |
|---|---|---|
| 1 | 茶楼 | Main board |
| 2 | 圆桌 | Open discussion |
| **3** | **评教** | **Course evaluation — the one that matters for enrollment** |
| 4 | 站务 | Site admin |
| 5 | 交易 | Non-commercial classifieds |

### Diagnostics

#### `check_connection()`
Checks WebVPN session, token, and account. Run this first when something breaks.

---

## How it works

### Why this layer exists

The Tree Hole APIs are hosted inside the campus network:

```
forum.fduhole.com → 10.107.13.152   ← campus-private address
auth.fduhole.com  → 10.107.13.152
danke.fduhole.com → 10.107.13.152
```

They are **physically unreachable** from outside. This project reimplements the WebVPN approach used by the [official DanXi client](https://github.com/DanXi-Dev/DanXi).

### Full chain

```
1. Read credentials (system keyring / env vars)
        ↓
2. UIS login at id.fudan.edu.cn
   getJsPublicKey → RSA-PKCS1 encrypt password → authExecute → loginToken
        ↓
3. authnEngine → CAS ticket (ST-xxxxx)
        ↓
4. Redeem ticket → WebVPN session cookie
        ↓
5. Rewrite API hostnames with AES-CFB
   https://auth.fduhole.com/api/login
   → https://webvpn.fudan.edu.cn/https/7772647670...c38/api/login
        ↓
6. Exchange Tree Hole credentials for a JWT → Bearer on all later calls
```

Step 5 in detail: AES-CFB with key = iv = `wrdvpnisthebest!`. The hostname is padded to a multiple of 16 **by character count** (not byte count), and the output is `iv_hex + ciphertext_hex[:2n]`.

> Sanity check: `auth.fduhole.com` always encrypts to
> `77726476706e69737468656265737421f1e2559469366c45760785a9d6562c38`.
> The first 32 chars are the hex of `wrdvpnisthebest!`. If yours differs, the implementation is wrong.

### Caching

Sessions and tokens live in `~/.danta-mcp/`:
- `cookies.json` — WebVPN session, treated as stale after 6 hours
- `token.json` — Tree Hole JWT, 20 days

Normal use does **not** re-login on every call.

### On campus

On campus Wi-Fi or eduroam, direct connections work; the WebVPN layer becomes a transparent fallback. No code changes needed.

---

## Security design

### Passwords are never written to disk in plaintext

They live in the OS credential store. The code reads them; it never writes copies. No credentials exist in the repo (see `.gitignore`).

### UIS login is attempted exactly once, then stops

**This is the most important design decision here.**

Fudan's UIS triggers a captcha after repeated failed logins. Once triggered, you must log in manually through a browser to clear it. Therefore:

```python
# authExecute is explicitly tries=1 — never retried
r = self._req("POST", ".../authExecute", tries=1, json={...})
```

If the response message contains 「验证码」 (captcha), the client **raises immediately and tells you to log in manually**. It will not hammer the endpoint.

Network-level retries (`tries=3`) apply only to WebVPN's **flaky transport**, never to login attempts.

### Cache permissions

Files under `~/.danta-mcp/` are chmod `600` (owner read/write only).

### Read-only

This project exposes **read tools only**. No posting, replying, or voting. The AI cannot speak on your behalf.

---

## Troubleshooting

### `No module named 'mcp.server.fastmcp'`

MCP SDK 2.x renamed `FastMCP` to `MCPServer`. `server.py` already imports both. If it still fails, your venv is being shadowed by an external `PYTHONPATH` → see next item.

### Tools don't show up / server exits immediately

**Almost always `PYTHONPATH` pollution.** Some MCP hosts inject their own `site-packages` into the child environment, shadowing this project's venv.

Fix: the config must use `-E` (ignore environment variables at interpreter startup):

```json
"args": ["-E", "/path/to/run_server.py"]
```

⚠️ Patching `sys.path` in code **does not work** — `sys.path` is finalized from `PYTHONPATH` before your first line runs.

### `❌ UIS requires a captcha`

Open https://id.fudan.edu.cn in a browser and log in once manually.

**Do not retry repeatedly** — it worsens the lockout.

### `login returned non-JSON`

The WebVPN session expired and you were bounced to the login page. The client rebuilds the session and retries once automatically. If it still fails:

```bash
rm -rf ~/.danta-mcp   # clear cache, force fresh login
```

### `IDP did not return a login context`

WebVPN instability (its root path `/` times out frequently). Wait and retry.

### After changing your UIS password

```bash
.venv/Scripts/python setup_credentials.py
```

Re-enter credentials.

---

## Known limitations

- **Tied to Fudan's current auth implementation.** If the university changes its login flow, this breaks; track [DanXi upstream](https://github.com/DanXi-Dev/DanXi) for updates.
- **No two-factor auth support.** Accounts with enhanced authentication raise `EnhancedAuthenticationRequiredException`.
- **WebVPN is inherently unstable.** Timeouts are normal; retries help but can't eliminate them.
- **Review coverage depends on students writing them.** Niche courses may have zero.
- Fully tested on Windows only; the macOS/Linux keyring path is implemented but untested.

---

## Credits

The WebVPN encryption scheme and UIS login flow are derived from [DanXi-Dev/DanXi](https://github.com/DanXi-Dev/DanXi), the official DanTa client (GPL-3.0). Thanks to the DanXi team.

This project is not affiliated with Fudan University or the DanXi development team.

---

## License

**GPL-3.0**

This project reuses core logic from DanXi (GPL-3.0); under the GPL's copyleft terms it must be released under the same license. See [LICENSE](./LICENSE).

---

## Disclaimer

This tool accesses only campus resources **you are already authorized to access** — equivalent to what you'd see by logging into the website yourself.

Follow Fudan University's network usage policies and the Tree Hole community guidelines. Users are responsible for their own conduct.
