"""
DanTa MCP server — 复旦旦挞（树洞 + 旦克课评）检索工具。

Exposes Fudan DanTa data to an AI agent as MCP tools: the Tree Hole forum
(anything students actually talk about — life, relationships, jobs, mental
health, transfers, second-hand goods) plus DanKe course reviews.

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
import time
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

DIVISIONS = {
    1: "茶楼（主板，什么都聊）",
    2: "圆桌（深入讨论）",
    3: "评教（课程/教师评价）",
    4: "站务",
    5: "交易（二手/合租/代购）",
}


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
        return f"❌ 凭据被拒绝：{e}。请检查凭据配置（setup_credentials.py）。"
    return f"❌ {type(e).__name__}: {e}"


_IMG = re.compile(r"!\[\]\([^)]*\)")
_MENTION = re.compile(r"##\d+")


def _clean(text: str | None, limit: int = 600) -> str:
    if not text:
        return "（无正文）"
    t = _IMG.sub("[图]", text).strip()
    return t[:limit] + ("…" if len(t) > limit else "")


def _stars(n: Any) -> str:
    try:
        n = int(n)
    except (TypeError, ValueError):
        return "—"
    return "★" * n + "☆" * (5 - n) if 0 <= n <= 5 else str(n)


def _as_list(r) -> list:
    if isinstance(r, list):
        return r
    if isinstance(r, dict):
        return r.get("items") or r.get("data") or []
    return []


def _fmt_floor(f: dict, content_limit=500) -> str:
    tag = f" [{f['special_tag']}]" if f.get("special_tag") else ""
    return (
        f"[洞 #{f.get('hole_id')} · {f.get('ranking', 0)}楼]{tag} "
        f"{f.get('time_created','')[:10]} · 👍{f.get('like', 0)}\n"
        f"{_clean(f.get('content'), content_limit)}"
    )


def _fmt_hole(h: dict, content_limit=300) -> str:
    tags = "/".join(t.get("name", "") for t in (h.get("tags") or [])[:5])
    first = (h.get("floors") or {}).get("first_floor") or {}
    return (
        f"[洞 #{h.get('hole_id')}] {h.get('time_created','')[:10]} · "
        f"回复 {h.get('reply', 0)} · {tags or '无标签'}\n"
        f"{_clean(first.get('content'), content_limit)}"
    )


# ==========================================================================
# 树洞 — 通用检索（生活/情感/就业/心理/转专业/二手 …… 什么都能搜）
# ==========================================================================
@mcp.tool()
def search_holes(keyword: str, limit: int = 15, accurate: bool = False,
                 within_days: int = 0) -> str:
    """在复旦树洞全站搜索。树洞是复旦学生的匿名社区，什么话题都有。

    适用于任何校园相关问题，不限于选课：
      生活   "食堂 好吃"、"宿舍 空调"、"洗衣房"、"校医院"
      情感   "异地恋"、"表白"、"分手"、"追人"
      就业   "实习 内推"、"秋招"、"offer 选择"、"考公"
      学业   "转专业"、"保研"、"绩点"、"退课"
      心理   "焦虑"、"emo"、"心理咨询"
      交友   "找搭子"、"社团"、"室友"
      交易   "二手"、"合租"、"出书"

    参数:
      accurate=True   精确匹配（关键词必须完整出现），默认模糊搜索
      within_days=N   只看最近 N 天（N=0 表示不限时间）
    """
    try:
        kw = {"length": max(1, min(limit, 50)), "accurate": accurate}
        if within_days > 0:
            now = int(time.time())
            kw["start_time"] = now - within_days * 86400
            kw["end_time"] = now
        rows = _as_list(client().search_floors(keyword, **kw))
    except Exception as e:
        return _err(e)

    if not rows:
        hint = "（试试关掉 accurate，或放宽 within_days）" if (accurate or within_days) else ""
        return f"树洞中没有搜到与「{keyword}」相关的内容。{hint}"

    scope = []
    if accurate:
        scope.append("精确匹配")
    if within_days > 0:
        scope.append(f"近 {within_days} 天")
    head = f"树洞搜索「{keyword}」{'（' + '，'.join(scope) + '）' if scope else ''}，{len(rows)} 条：\n"

    out = [head]
    for f in rows:
        out.append(_fmt_floor(f) + "\n")
    out.append("用 get_hole(hole_id) 读某个洞的完整讨论（回复往往才是重点）。")
    return "\n".join(out)


@mcp.tool()
def get_hole(hole_id: int, limit: int = 40) -> str:
    """读某个树洞的完整讨论（所有楼层）。

    树洞的价值常在回复里——楼主提问，楼里的人给经验。
    搜到感兴趣的洞后一定要用这个读全文。
    """
    try:
        floors = _as_list(client().floors(hole_id, start=0,
                                          length=max(1, min(limit, 100))))
    except Exception as e:
        return _err(e)
    if not floors:
        return f"树洞 #{hole_id} 没有内容或不存在。"

    out = [f"# 树洞 #{hole_id}（{len(floors)} 层）\n"]
    for f in floors:
        who = f.get("anonyname") or "?"
        tag = f" [{f['special_tag']}]" if f.get("special_tag") else ""
        reply = f" ↩回复{f['reply_to']}" if f.get("reply_to") else ""
        out.append(
            f"── {f.get('ranking',0)}楼 · {who}{tag}{reply} · "
            f"{f.get('time_created','')[:16].replace('T',' ')} · 👍{f.get('like',0)}\n"
            f"{_clean(f.get('content'), 900)}\n"
        )
    return "\n".join(out)


@mcp.tool()
def browse_by_tag(tag: str, limit: int = 15, division_id: int = 1) -> str:
    """按话题标签浏览最新树洞。比关键词搜索更适合"逛"某个话题。

    常用标签：提问 求助 生活 学习 恋爱 情感 吐槽 发牢骚 emo 交友
              选课 转专业 保研 期末考试 出分 二手交易 找搭子 军训 家教
    用 list_hot_tags() 查看当前最热的标签。
    """
    try:
        holes = _as_list(client().list_holes(
            division_id=division_id, length=max(1, min(limit, 50)), tag=tag))
    except Exception as e:
        return _err(e)
    if not holes:
        return f"标签「{tag}」下没有找到树洞。用 list_hot_tags() 看看有哪些标签。"

    out = [f"标签「{tag}」下最新 {len(holes)} 个树洞：\n"]
    for h in holes:
        out.append(_fmt_hole(h) + "\n")
    out.append("用 get_hole(hole_id) 读完整讨论。")
    return "\n".join(out)


@mcp.tool()
def list_hot_tags(limit: int = 40, keyword: str = "") -> str:
    """列出树洞最热门的话题标签（按热度排序），可用 keyword 过滤。

    用来了解树洞上大家都在聊什么，或给 browse_by_tag 找合适的标签。
    例如 list_hot_tags(keyword="实习") 找所有和实习相关的标签。
    """
    try:
        tags = _as_list(client().tags())
    except Exception as e:
        return _err(e)
    if keyword:
        tags = [t for t in tags if keyword in (t.get("name") or "")]
    tags.sort(key=lambda x: x.get("temperature", 0), reverse=True)
    tags = tags[: max(1, min(limit, 100))]
    if not tags:
        return f"没有找到包含「{keyword}」的标签。"

    head = f"热门标签{'（含「' + keyword + '」）' if keyword else ''}，{len(tags)} 个：\n"
    body = "\n".join(f"  {t.get('name')}  (热度 {t.get('temperature', 0)})"
                     for t in tags)
    return head + body + "\n\n用 browse_by_tag(tag) 浏览某个标签下的树洞。"


@mcp.tool()
def browse_division(division_id: int = 1, limit: int = 15) -> str:
    """浏览某个板块的最新树洞（看当下大家在聊什么）。

    板块：1=茶楼(主板,什么都聊) 2=圆桌(深入讨论) 3=评教(课程评价)
          4=站务 5=交易(二手/合租)
    """
    try:
        holes = _as_list(client().list_holes(
            division_id=division_id, length=max(1, min(limit, 50))))
    except Exception as e:
        return _err(e)
    if not holes:
        return f"板块 {division_id} 没有返回内容。"

    name = DIVISIONS.get(division_id, f"板块 {division_id}")
    out = [f"{name} 最新 {len(holes)} 个树洞：\n"]
    for h in holes:
        out.append(_fmt_hole(h) + "\n")
    return "\n".join(out)


@mcp.tool()
def list_divisions() -> str:
    """列出树洞的所有板块及其 ID。"""
    try:
        ds = client().divisions()
    except Exception as e:
        return _err(e)
    return "树洞板块：\n" + "\n".join(
        f"  [{d.get('division_id')}] {d.get('name')} — {d.get('description','')}"
        for d in ds
    )


# ==========================================================================
# 旦克 — 课程评价
# ==========================================================================
@mcp.tool()
def search_courses(keyword: str, limit: int = 10) -> str:
    """搜索复旦课程（旦克课程库）。返回课程组列表含评价数量。

    选课调研第一步。keyword 可以是课程名、课程代码、关键词，
    例如 "微积分"、"MATH120012"、"思想道德"。
    注意先看评价数，为 0 的课没有参考价值。
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
    out.append("\n用 get_course_reviews(course_group_id) 查看详细评价。")
    return "\n".join(out)


@mcp.tool()
def get_course_reviews(course_group_id: int, max_reviews: int = 12) -> str:
    """获取某门课的全部评价（按教师/学期分组），含评分、给分情况、正文。

    评分维度：综合/内容/工作量/考核，remark 是推荐指数。
    course_group_id 来自 search_courses。
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
