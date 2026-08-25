"""
Build a self-contained HTML citation report from DanTa search results.

Every quoted line keeps its provenance: hole id, floor number, author alias,
timestamp, likes, and a link back to the web frontend. Nothing is paraphrased
here — the report shows raw forum text so a human can audit the summary.

Copyright (C) 2026  danta-mcp contributors

This program is free software: you can redistribute it and/or modify it under
the terms of the GNU General Public License as published by the Free Software
Foundation, either version 3 of the License, or (at your option) any later
version. See <https://www.gnu.org/licenses/gpl-3.0.html>.
"""
import html
import re
import time
from typing import Iterable

WEB_BASE = "https://www.fduhole.com"

_IMG = re.compile(r"!\[\]\(([^)]*)\)")
_MENTION = re.compile(r"##(\d+)")


def hole_url(hole_id) -> str:
    return f"{WEB_BASE}/hole/{hole_id}"


def _render_content(text: str | None) -> str:
    if not text:
        return '<span class="empty">（无正文）</span>'
    t = html.escape(text.strip())
    t = _IMG.sub('<span class="img">🖼</span>', t)
    t = _MENTION.sub(r'<span class="mention">↩##\1</span>', t)
    return t.replace("\n", "<br>")


def _floor_block(f: dict, *, highlight: str | None = None) -> str:
    hid = f.get("hole_id")
    rank = f.get("ranking", 0)
    who = html.escape(str(f.get("anonyname") or "?"))
    ts = (f.get("time_created") or "")[:10]
    like = f.get("like", 0)
    stag = f.get("special_tag")
    badge = f'<em class="stag">{html.escape(str(stag))}</em>' if stag else ""
    like_html = f'<span class="like">👍 {like}</span>' if like else ""
    key = ' data-key="1"' if highlight else ""
    return f"""
      <article class="floor"{key}>
        <div class="meta">
          <a class="src" href="{hole_url(hid)}" target="_blank" rel="noopener">#{hid}</a>
          <span class="rank">{rank}楼</span>
          <span class="who">{who}</span>{badge}
          <span class="when">{html.escape(ts)}</span>
          {like_html}
        </div>
        <div class="body">{_render_content(f.get('content'))}</div>
      </article>"""


def _section(idx: int, title: str, subtitle: str, blocks: Iterable[str]) -> str:
    body = "\n".join(blocks) or '<p class="empty">（无结果）</p>'
    sub = f'<p class="sub">{html.escape(subtitle)}</p>' if subtitle else ""
    return f"""
    <section>
      <h2><span class="num">{idx}</span>{html.escape(title)}</h2>
      {sub}
      {body}
    </section>"""


CSS = """
*{box-sizing:border-box;margin:0;padding:0}
body{background:#fbfbfd;color:#1d1d20;
  font:16px/1.8 -apple-system,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;
  padding:44px 20px 80px;-webkit-font-smoothing:antialiased}
.wrap{max-width:820px;margin:0 auto}

header{margin-bottom:40px}
h1{font-size:32px;line-height:1.35;font-weight:750;letter-spacing:-.5px;margin-bottom:12px}
.gen{color:#71717a;font-size:13.5px;display:flex;flex-wrap:wrap;gap:6px;align-items:center}
.pill{background:#eef0f4;border-radius:20px;padding:2px 11px;font-size:12.5px;color:#52525b}

/* ---- answer cards ---- */
.card{border-radius:16px;padding:26px 28px;margin-bottom:20px;border:1px solid #e6e6ec;
  background:#fff;box-shadow:0 1px 3px rgba(0,0,0,.04),0 8px 24px rgba(0,0,0,.03)}
.card h2{font-size:19px;font-weight:700;margin-bottom:14px;display:flex;
  align-items:center;gap:9px;letter-spacing:-.2px}
.card.ok{border-left:4px solid #16a34a}
.card.ok h2{color:#15803d}
.card.warn{border-left:4px solid #ea580c}
.card.warn h2{color:#c2410c}
.card p{margin-bottom:10px}
.card ul{padding-left:4px;list-style:none}
.card li{margin:9px 0;padding-left:22px;position:relative;line-height:1.75}
.card li::before{content:"";position:absolute;left:6px;top:11px;width:5px;height:5px;
  border-radius:50%;background:#a1a1aa}

.addr{background:#0f172a;color:#e2e8f0;border-radius:12px;padding:20px 22px;margin:16px 0;
  font:600 17px/2.1 ui-monospace,"SF Mono",Consolas,"Microsoft YaHei",monospace;
  white-space:pre-wrap;letter-spacing:.3px}
.addr .hl{color:#7dd3fc}

.tip{background:#fff7ed;border:1px solid #fed7aa;border-radius:11px;
  padding:14px 17px;margin-top:14px;font-size:15px;line-height:1.7;color:#7c2d12}

/* ---- table ---- */
table{border-collapse:separate;border-spacing:0;width:100%;margin:14px 0;font-size:14.5px;
  border:1px solid #e6e6ec;border-radius:12px;overflow:hidden}
th{background:#f4f4f7;font-weight:650;font-size:13.5px;color:#3f3f46}
th,td{padding:12px 15px;text-align:left;border-bottom:1px solid #eeeef2}
tr:last-child td{border-bottom:none}
tr.me td{background:#f0fdf4}
td.mono{font-family:ui-monospace,Consolas,"Microsoft YaHei",monospace;font-size:13.5px}

/* ---- sections ---- */
section{margin-top:42px}
h2{font-size:20px;font-weight:700;letter-spacing:-.2px;
  display:flex;align-items:center;gap:11px;margin-bottom:6px}
.num{background:#1d1d20;color:#fff;width:26px;height:26px;border-radius:8px;
  display:inline-flex;align-items:center;justify-content:center;
  font-size:13.5px;font-weight:700;flex:none}
.sub{color:#71717a;font-size:14px;margin:0 0 18px 37px;line-height:1.6}

/* ---- floor cards ---- */
.floor{background:#fff;border:1px solid #e8e8ee;border-radius:13px;
  padding:16px 19px;margin-bottom:12px}
.floor[data-key]{border-color:#bbf7d0;background:#f7fefa}
.meta{display:flex;flex-wrap:wrap;gap:9px;align-items:center;
  font-size:12.5px;color:#71717a;margin-bottom:10px;
  padding-bottom:10px;border-bottom:1px solid #f2f2f6}
a.src{color:#2563eb;text-decoration:none;font-weight:700;
  font-family:ui-monospace,Consolas,monospace;font-size:13px}
a.src:hover{text-decoration:underline}
.rank{background:#f4f4f7;border-radius:5px;padding:1px 7px;font-size:12px;color:#52525b}
.who{color:#7c3aed;font-weight:600}
.stag{background:#fef3c7;color:#92400e;border-radius:5px;padding:1px 7px;
  font-size:11.5px;font-style:normal;font-weight:600}
.when{margin-left:auto;font-variant-numeric:tabular-nums}
.like{color:#52525b}
.body{font-size:15px;line-height:1.85;word-break:break-word;color:#27272a}
.img{opacity:.5}
.mention{color:#2563eb;opacity:.6;font-size:13px;font-family:ui-monospace,monospace}
.empty{color:#a1a1aa;font-style:italic}

footer{margin-top:56px;padding-top:22px;border-top:1px solid #e6e6ec;
  color:#71717a;font-size:13px;line-height:1.8}
footer p{margin-bottom:7px}
footer strong{color:#3f3f46}

@media (prefers-color-scheme:dark){
  body{background:#0b0b0e;color:#e8e8ec}
  .card,.floor,table{background:#141418;border-color:#26262d}
  .card{box-shadow:none}
  .floor[data-key]{background:#0f1a13;border-color:#1c4a2c}
  th{background:#1a1a20;color:#a1a1aa}
  th,td{border-color:#26262d}
  tr.me td{background:#0f1a13}
  .pill{background:#1f1f26;color:#a1a1aa}
  .meta{border-color:#26262d}
  .rank{background:#1f1f26;color:#a1a1aa}
  .body{color:#d4d4d8}
  .num{background:#e8e8ec;color:#0b0b0e}
  .tip{background:#1f1710;border-color:#5a3a1a;color:#fdba74}
  .stag{background:#3a2e10;color:#fcd34d}
  h1,.card h2{color:#f4f4f5}
  .card.ok h2{color:#4ade80}
  .card.warn h2{color:#fb923c}
  a.src{color:#60a5fa}
  .who{color:#c4b5fd}
  footer strong{color:#a1a1aa}
}
"""


def build_report(title: str, summary_html: str,
                 sections: list[tuple[str, str, list[dict]]],
                 note: str = "", source_count: int | None = None) -> str:
    secs = "\n".join(
        _section(i, h, sub, [_floor_block(f) for f in floors])
        for i, (h, sub, floors) in enumerate(sections, 1)
    )
    gen = time.strftime("%Y-%m-%d %H:%M")
    n = source_count if source_count is not None else sum(len(s[2]) for s in sections)
    footer_note = f"<p>{note}</p>" if note else ""
    return f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)}</title><style>{CSS}</style></head>
<body><div class="wrap">
<header>
  <h1>{html.escape(title)}</h1>
  <div class="gen">
    <span class="pill">复旦树洞实时检索</span>
    <span class="pill">{n} 条原始引用</span>
    <span>· {gen} 由 danta-mcp 生成</span>
  </div>
</header>
{summary_html}
{secs}
<footer>
  <p><strong>数据来源</strong>　复旦树洞 forum.fduhole.com，经 WebVPN 实时检索。
     洞号可点击跳转网页版（需登录）。</p>
  {footer_note}
  <p><strong>免责</strong>　树洞内容为匿名学生个人经验，非官方信息，请以学校正式通知为准。</p>
</footer>
</div></body></html>"""
