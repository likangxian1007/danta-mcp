"""
DanTa MCP server — 复旦旦挞（树洞 + 旦克课评）检索工具。

Exposes Fudan DanTa data to an AI agent as MCP tools, so the agent can research
courses and campus discussions autonomously (built for 选课).

Transport: stdio.

Copyright (C) 2026  danta-mcp contributors

This program is free software: you can redistribute it and/or modify it under
the terms of the GNU General Public License as published by the Free Software
Foundation, either version 3 of the License, or (at your option) any later
version. See <https://www.gnu.org/licenses/gpl-3.0.html>.
"""
from __future__ import annotations

import json
import re
from typing import Any

# MCP SDK moved FastMCP -> MCPServer in 2.x. Support both.
try:
    from mcp.server.fastmcp import FastMCP as _Server  # SDK 1.x
except ModuleNotFoundError:
    from mcp.server.mcpserver import MCPServer as _Server  # SDK 2.x

from danta_client import (
    DantaClient, DantaError, CaptchaRequired, CredentialsInvalid,
)

mcp = _Server("danta")
_client: DantaClient | None = None


def client() -> DantaClient:
    global _client
    if _client is None:
        _client = DantaClient()
    return _client


def _err(e: Exception) -> str:
    if isinstance(e, CaptchaRequired):
        return ("❌ UIS 触发了验证码。请用浏览器打开 https://id.fudan.edu.cn "
                "手动登录一次，然后重试。（不要反复重试，会加重锁定）")
    if isinstance(e, CredentialsInvalid):
        return f"❌ 凭据被拒绝：{e}。请检查 Windows 凭据管理器中的 DanTaMCP_UIS / DanTaMCP_Hole。"
    return f"❌ {type(e).__name__}: {e}"


# 树洞正文里的图片/表情标记，检索时是噪音
_IMG = re.compile(r"!\[\]\([^)]*\)")


def _clean(text: str | None, limit: int = 600) -> str:
    if not text:
        return ""
    t = _IMG.sub("[图]", text).strip()
    return t[:limit] + ("…" if len(t) > limit else "")


def _stars(n: Any) -> str:
    try:
        n = int(n)
    except (TypeError, ValueError):
        return "—"
    return "★" * n + "☆" * (5 - n) if 0 <= n <= 5 else str(n)


# ==========================================================================
# 旦克 — 课程评价（选课主力）
# ==========================================================================
@mcp.tool()
def search_courses(keyword: str, limit: int = 10) -> str:
    """搜索复旦课程（旦克课程库）。返回课程组列表含评价数量。

    选课调研的第一步：用课程名/课程代码/关键词找到课，再用 get_course_reviews
    看具体评价。keyword 例如 "微积分"、"高等代数"、"MATH120012"、"思想道德"。
    """
    try:
        r = client().search_courses(keyword, page_size=max(1, min(limit, 30)))
    except Exception as e:
        return _err(e)
    items = r.get("items") or []
    if not items:
        return f"没有找到与「{keyword}」相关的课程。"
    out = [f"找到 {len(items)} 门与「{keyword}」相关的课程：\n"]
    for it in items:
        out.append(
            f"[{it['id']}] {it['name']}  ({it.get('code','')})\n"
            f"    院系: {it.get('department','?')} | 学分: {it.get('credits')} | "
            f"校区: {it.get('campus_name') or '?'}\n"
            f"    开课班次: {it.get('course_count',0)} | 评价数: {it.get('review_count',0)}"
        )
    out.append("\n用 get_course_reviews(course_group_id) 查看某门课的详细评价。")
    return "\n".join(out)


@mcp.tool()
def get_course_reviews(course_group_id: int, max_reviews: int = 12) -> str:
    """获取某门课的全部评价（按教师/学期分组），含评分、给分情况、正文。

    这是选课决策的核心数据：评分维度为 综合/内容/工作量/考核，
    remark 是该评价的推荐指数。course_group_id 来自 search_courses。
    """
    try:
        g = client().course_group(course_group_id)
    except Exception as e:
        return _err(e)

    out = [
        f"# {g.get('name')} ({g.get('code','')})",
        f"院系: {g.get('department','?')} | 学分: {g.get('credits')} | "
        f"总评价数: {g.get('review_count', 0)}",
        "",
    ]
    courses = g.get("course_list") or []
    if not courses:
        return "\n".join(out) + "\n（暂无开课班次数据）"

    shown = 0
    for c in courses:
        reviews = c.get("review_list") or []
        out.append(
            f"## 教师: {c.get('teachers','?')} | "
            f"{c.get('year','?')} 学年第 {c.get('semester','?')} 学期 | "
            f"{c.get('credit')} 学分 | {c.get('code_id','')}"
        )
        if not reviews:
            out.append("  （该班次暂无评价）\n")
            continue
        for rv in reviews:
            if shown >= max_reviews:
                out.append(f"\n…还有更多评价未显示（已显示 {shown} 条）。")
                return "\n".join(out)
            rank = rv.get("rank") or {}
            out.append(
                f"\n### {rv.get('title') or '(无标题)'}   "
                f"[推荐 {rv.get('remark', 0)} | 赞 {rv.get('vote', 0)}]\n"
                f"  综合 {_stars(rank.get('overall'))}  "
                f"内容 {_stars(rank.get('content'))}  "
                f"工作量 {_stars(rank.get('workload'))}  "
                f"考核 {_stars(rank.get('assessment'))}\n"
                f"  {rv.get('time_created','')[:10]}\n\n"
                f"{_clean(rv.get('content'), 1200)}"
            )
            shown += 1
        out.append("")
    return "\n".join(out)


# ==========================================================================
# 树洞 — 论坛检索
# ==========================================================================
@mcp.tool()
def search_holes(keyword: str, limit: int = 15) -> str:
    """在复旦树洞全站搜索包含关键词的帖子内容。

    适合调研课程口碑、老师风评、选课经验、校园生活等真实学生讨论。
    例如 "微积分 期末"、"体育课 推荐"、"选课 攻略"。
    """
    try:
        rows = client().search_floors(keyword, length=max(1, min(limit, 50)))
    except Exception as e:
        return _err(e)
    rows = rows if isinstance(rows, list) else (rows.get("items") or [])
    if not rows:
        return f"树洞中没有搜到与「{keyword}」相关的内容。"
    out = [f"树洞中找到 {len(rows)} 条与「{keyword}」相关的内容：\n"]
    for f in rows:
        out.append(
            f"[洞 #{f.get('hole_id')} / {f.get('ranking', 0)}楼] "
            f"{f.get('time_created','')[:10]}  👍{f.get('like',0)}\n"
            f"{_clean(f.get('content'))}\n"
        )
    out.append("用 get_hole(hole_id) 查看整个树洞的完整讨论。")
    return "\n".join(out)


@mcp.tool()
def get_hole(hole_id: int, limit: int = 40) -> str:
    """获取某个树洞的完整discussion（所有楼层）。hole_id 来自 search_holes。"""
    try:
        c = client()
        floors = c.floors(hole_id, start=0, length=max(1, min(limit, 100)))
    except Exception as e:
        return _err(e)
    floors = floors if isinstance(floors, list) else (floors.get("items") or [])
    if not floors:
        return f"树洞 #{hole_id} 没有内容或不存在。"
    out = [f"# 树洞 #{hole_id}（{len(floors)} 层）\n"]
    for f in floors:
        who = f.get("anonyname") or "?"
        tag = f" [{f['special_tag']}]" if f.get("special_tag") else ""
        out.append(
            f"── {f.get('ranking',0)}楼 · {who}{tag} · "
            f"{f.get('time_created','')[:16].replace('T',' ')} · 👍{f.get('like',0)}\n"
            f"{_clean(f.get('content'), 800)}\n"
        )
    return "\n".join(out)


@mcp.tool()
def list_divisions() -> str:
    """列出树洞的所有板块（分区）及其 ID。"""
    try:
        ds = client().divisions()
    except Exception as e:
        return _err(e)
    return "树洞板块：\n" + "\n".join(
        f"  [{d.get('division_id')}] {d.get('name')} — {d.get('description','')}"
        for d in ds
    )


@mcp.tool()
def browse_division(division_id: int = 1, limit: int = 15) -> str:
    """浏览某个板块的最新树洞。division_id: 1=茶楼 2=圆桌 3=评教 4=站务 5=交易。

    评教板块(3)对选课特别有用。
    """
    try:
        holes = client().list_holes(division_id=division_id,
                                    length=max(1, min(limit, 50)))
    except Exception as e:
        return _err(e)
    holes = holes if isinstance(holes, list) else (holes.get("items") or [])
    if not holes:
        return f"板块 {division_id} 没有返回内容。"
    out = [f"板块 {division_id} 的最新 {len(holes)} 个树洞：\n"]
    for h in holes:
        tags = "/".join(t.get("name", "") for t in (h.get("tags") or [])[:4])
        first = (h.get("floors") or {}).get("first_floor") or {}
        out.append(
            f"[洞 #{h.get('hole_id')}] {h.get('time_created','')[:10]} "
            f"· 回复 {h.get('reply', 0)} · 标签 {tags or '—'}\n"
            f"{_clean(first.get('content'), 300)}\n"
        )
    return "\n".join(out)


@mcp.tool()
def check_connection() -> str:
    """检查旦挞连接状态：WebVPN 会话、登录 token、账号信息。排障用。"""
    try:
        c = client()
        tok = c.ensure_token()
        me = c.me()
        divs = c.divisions()
        return (
            "✅ 连接正常\n"
            f"  WebVPN: 已建立会话\n"
            f"  Token: {tok[:24]}…\n"
            f"  用户 ID: {me.get('user_id')}\n"
            f"  可用板块: {len(divs)} 个"
        )
    except Exception as e:
        return _err(e)


if __name__ == "__main__":
    mcp.run()
