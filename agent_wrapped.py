#!/usr/bin/env python3
"""agent-wrapped — Your AI coding agent, wrapped. Locally.

Reads your AI coding-agent transcripts and prints a personal usage report:
model split, peak hours, prompt style, plan-mode %, top phrases, longest
session, context peaks, API-list value, and more.

v0.1 supports Claude Code (~/.claude/projects/). Codex CLI and Cursor
support planned — see the roadmap in README.md.

All computation runs locally. No network calls. Zero dependencies.
See PRIVACY.md for the full breakdown.

Repository: https://github.com/mallikharjun073/agent-wrapped
License:    MIT
"""
__version__ = "0.1.0"

import argparse
import io
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

HISTORY = Path.home() / ".agent-wrapped" / "history.jsonl"

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
else:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

PROJECTS = Path.home() / ".claude" / "projects"
POLITE = re.compile(r"\b(thanks|thank you|please|thx|ty)\b", re.I)
STEER = re.compile(r"^\s*(no|stop|wait|actually|don'?t|nope|hold on)\b", re.I)
SLASH = re.compile(r"^\s*/[a-zA-Z][\w-]*")
WORD = re.compile(r"\w+")

PRICES = {
    "opus":   {"in": 15.0, "out": 75.0, "cache_read": 1.50, "cache_write": 18.75},
    "sonnet": {"in": 3.0,  "out": 15.0, "cache_read": 0.30, "cache_write": 3.75},
    "haiku":  {"in": 1.0,  "out": 5.0,  "cache_read": 0.10, "cache_write": 1.25},
}


def price_tier(model):
    if not model:
        return "opus"
    m = model.lower()
    if "haiku" in m:
        return "haiku"
    if "sonnet" in m:
        return "sonnet"
    return "opus"


def cost_usd(model, inp, out, cache_read, cache_create):
    p = PRICES[price_tier(model)]
    return (inp * p["in"] + out * p["out"] + cache_read * p["cache_read"] + cache_create * p["cache_write"]) / 1_000_000
STOP = {
    "the","a","an","to","of","in","and","or","for","is","it","this","that",
    "with","on","at","from","by","as","be","are","was","were","i","you","we",
    "my","me","if","not","no","do","does","can","will","would","should","could",
    "have","has","had","but","so","also","just","like","get","use","using","one",
    "make","made","need","want","then","when","where","which","what","how","why",
    "there","here","them","their","its","been","being","he","she","they","up","out",
    "about","into","over","than","only","any","all","some","other","new","old",
    "add","added","adding","see","seen","let","let's","tell","give","take",
}


def extract_text(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
        return "\n".join(parts)
    return ""


def parse_ts(s):
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


def iter_sessions(cutoff, project_filter):
    if not PROJECTS.exists():
        return
    for proj_dir in PROJECTS.iterdir():
        if not proj_dir.is_dir():
            continue
        if project_filter and project_filter.lower() not in proj_dir.name.lower():
            continue
        for f in proj_dir.glob("*.jsonl"):
            mtime = datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc)
            if cutoff and mtime < cutoff:
                continue
            yield proj_dir.name, f


def analyze(days, project_filter):
    cutoff = None
    if days:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    stats = {
        "sessions": 0,
        "projects": set(),
        "user_msgs": 0,
        "assistant_msgs": 0,
        "models": Counter(),
        "hour_hist": Counter(),
        "weekday_hist": Counter(),
        "prompt_words": [],
        "short_prompts": 0,
        "polite": 0,
        "steer": 0,
        "caps_prompts": 0,
        "tool_use": Counter(),
        "plan_mode": 0,
        "max_parallel_agents": 0,
        "sessions_duration": [],
        "longest_run_hours": 0,
        "longest_run_session": "",
        "phrases": Counter(),
        "session_peaks": [],
        "cost_by_model": Counter(),
        "cost_total": 0.0,
        "cost_by_tier": Counter(),
        "first_prompt_words": [],
        "slash_commands": 0,
        "session_turns": [],
        "first_ts": None,
        "last_ts": None,
    }

    for proj, f in iter_sessions(cutoff, project_filter):
        stats["sessions"] += 1
        stats["projects"].add(proj)
        session_first = None
        session_last = None
        session_peak_ctx = 0
        session_peak_model = ""
        session_cache_read = 0
        session_input_total = 0
        session_first_prompt_recorded = False
        session_turn_count = 0

        try:
            lines = f.read_text(encoding="utf-8", errors="ignore").splitlines()
        except OSError:
            continue

        for line in lines:
            if not line.strip():
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue

            ts = parse_ts(rec.get("timestamp"))
            if ts:
                session_first = ts if not session_first else min(session_first, ts)
                session_last = ts if not session_last else max(session_last, ts)
                stats["first_ts"] = ts if not stats["first_ts"] else min(stats["first_ts"], ts)
                stats["last_ts"] = ts if not stats["last_ts"] else max(stats["last_ts"], ts)

            rtype = rec.get("type")
            msg = rec.get("message") or {}

            if rtype == "user":
                text = extract_text(msg.get("content"))
                if not text or text.startswith("<"):
                    continue
                stats["user_msgs"] += 1
                session_turn_count += 1
                if SLASH.match(text):
                    stats["slash_commands"] += 1
                words = WORD.findall(text)
                wc = len(words)
                stats["prompt_words"].append(wc)
                if not session_first_prompt_recorded:
                    stats["first_prompt_words"].append(wc)
                    session_first_prompt_recorded = True
                if wc < 10:
                    stats["short_prompts"] += 1
                if POLITE.search(text):
                    stats["polite"] += 1
                if STEER.match(text):
                    stats["steer"] += 1
                letters = [c for c in text if c.isalpha()]
                if letters and sum(1 for c in letters if c.isupper()) / len(letters) > 0.6 and len(letters) > 10:
                    stats["caps_prompts"] += 1
                if ts:
                    local = ts.astimezone()
                    stats["hour_hist"][local.hour] += 1
                    stats["weekday_hist"][local.strftime("%a")] += 1
                lowered = [w.lower() for w in words if w.lower() not in STOP and len(w) > 2]
                for i in range(len(lowered) - 2):
                    stats["phrases"][" ".join(lowered[i:i+3])] += 1

            elif rtype == "assistant":
                stats["assistant_msgs"] += 1
                model = msg.get("model")
                if model:
                    stats["models"][model] += 1
                usage = msg.get("usage") or {}
                cache_read = usage.get("cache_read_input_tokens") or 0
                cache_create = usage.get("cache_creation_input_tokens") or 0
                inp = usage.get("input_tokens") or 0
                turn_ctx = inp + cache_read + cache_create
                if turn_ctx > session_peak_ctx:
                    session_peak_ctx = turn_ctx
                    session_peak_model = model or session_peak_model
                session_cache_read += cache_read
                session_input_total += inp + cache_read + cache_create
                out = usage.get("output_tokens") or 0
                c = cost_usd(model, inp, out, cache_read, cache_create)
                if c > 0:
                    stats["cost_total"] += c
                    if model:
                        stats["cost_by_model"][model] += c
                    stats["cost_by_tier"][price_tier(model)] += c
                content = msg.get("content") or []
                agent_count = 0
                if isinstance(content, list):
                    for b in content:
                        if isinstance(b, dict) and b.get("type") == "tool_use":
                            name = b.get("name", "")
                            stats["tool_use"][name] += 1
                            if name == "Agent":
                                agent_count += 1
                            if name == "ExitPlanMode":
                                stats["plan_mode"] += 1
                if agent_count > stats["max_parallel_agents"]:
                    stats["max_parallel_agents"] = agent_count

        if session_first and session_last:
            dur = (session_last - session_first).total_seconds() / 3600
            stats["sessions_duration"].append(dur)
            if dur > stats["longest_run_hours"]:
                stats["longest_run_hours"] = dur
                stats["longest_run_session"] = f"{proj} / {f.stem[:8]}"
        if session_turn_count > 0:
            stats["session_turns"].append(session_turn_count)
        if session_peak_ctx > 0:
            window = 1_000_000 if session_peak_model and "1m" in session_peak_model.lower() else 200_000
            cache_hit = (session_cache_read / session_input_total) if session_input_total else 0.0
            stats["session_peaks"].append({
                "peak": session_peak_ctx,
                "pct": min(100.0, 100.0 * session_peak_ctx / window),
                "window": window,
                "cache_hit": cache_hit,
            })

    return stats


def bar(n, mx, width=20):
    if mx == 0:
        return ""
    filled = int(round(n / mx * width))
    return "█" * filled + "·" * (width - filled)


def render(s, top):
    out = []
    p = out.append
    p("")
    p("╔══════════════════════════════════════════════════════════╗")
    p("║              AGENT WRAPPED  ·  Claude Code                ║")
    p("╚══════════════════════════════════════════════════════════╝")
    p("")

    if not s["sessions"]:
        p("No sessions found in ~/.claude/projects/")
        return "\n".join(out)

    span = ""
    if s["first_ts"] and s["last_ts"]:
        span = f"  ({s['first_ts'].date()} → {s['last_ts'].date()})"

    p(f"Sessions        {s['sessions']:>6}   across {len(s['projects'])} project(s){span}")
    p(f"Your prompts    {s['user_msgs']:>6}")
    p(f"Agent replies   {s['assistant_msgs']:>6}")
    if s["prompt_words"]:
        avg = sum(s["prompt_words"]) / len(s["prompt_words"])
        p(f"Avg prompt      {avg:>6.1f} words   short (<10w): {100*s['short_prompts']/max(s['user_msgs'],1):.0f}%")

    p("")
    p("── MODELS ────────────────────────────────────────────────")
    total_m = sum(s["models"].values()) or 1
    for m, c in s["models"].most_common(6):
        pct = 100 * c / total_m
        p(f"  {m:<28} {pct:>5.1f}%  {bar(c, s['models'].most_common(1)[0][1])}")

    p("")
    p("── WHEN YOU SHIP ─────────────────────────────────────────")
    if s["hour_hist"]:
        peak_h = s["hour_hist"].most_common(1)[0][0]
        night_owl = sum(c for h, c in s["hour_hist"].items() if h >= 22 or h < 2)
        pct_night = 100 * night_owl / max(sum(s["hour_hist"].values()), 1)
        p(f"  Peak hour     {peak_h:02d}:00")
        p(f"  Night owl %   {pct_night:.0f}%  (10pm-2am)")
        mx = max(s["hour_hist"].values())
        for h in range(24):
            c = s["hour_hist"].get(h, 0)
            p(f"  {h:02d}h  {bar(c, mx, 30)}  {c}")
    if s["weekday_hist"]:
        top_day = s["weekday_hist"].most_common(1)[0][0]
        p(f"  Top day       {top_day}")

    p("")
    p("── STYLE ─────────────────────────────────────────────────")
    up = s["user_msgs"] or 1
    p(f"  Politeness    {100*s['polite']/up:>5.0f}%   thanked/please  ({s['polite']} times)")
    p(f"  Course-corr   {100*s['steer']/up:>5.0f}%   no/stop/wait/actually ({s['steer']} times)")
    p(f"  Caps-lock     {100*s['caps_prompts']/up:>5.0f}%   heated prompts ({s['caps_prompts']} times)")
    p(f"  Plan-mode     {s['plan_mode']} explicit ExitPlanMode calls")
    p(f"  Max parallel  {s['max_parallel_agents']} agents in one turn")
    if s["sessions_duration"]:
        p(f"  Longest run   {s['longest_run_hours']:.1f}h  ({s['longest_run_session']})")

    p("")
    p("── TOP TOOLS ─────────────────────────────────────────────")
    tot_t = sum(s["tool_use"].values()) or 1
    for t, c in s["tool_use"].most_common(10):
        p(f"  {t:<24} {c:>5}  {100*c/tot_t:>4.1f}%")

    p("")
    p(f"── TOP PHRASES (3-word) ──────────────────────────────────")
    for ph, c in s["phrases"].most_common(top):
        p(f"  {c:>4}  {ph}")

    p("")
    return "\n".join(out)


def context_summary(peaks):
    if not peaks:
        return None
    pcts = [p["pct"] for p in peaks]
    hits = [p["cache_hit"] for p in peaks if p["cache_hit"] > 0]
    under30 = sum(1 for x in pcts if x < 30)
    under50 = sum(1 for x in pcts if x < 50)
    over70 = sum(1 for x in pcts if x >= 70)
    return {
        "n": len(peaks),
        "avg_pct": sum(pcts) / len(pcts),
        "median_pct": sorted(pcts)[len(pcts) // 2],
        "max_pct": max(pcts),
        "pct_under_30": 100 * under30 / len(pcts),
        "pct_under_50": 100 * under50 / len(pcts),
        "pct_over_70": 100 * over70 / len(pcts),
        "cache_hit": (sum(hits) / len(hits)) if hits else 0.0,
    }


def derive_insights(s, ctx):
    good, warn, info = [], [], []
    up = s["user_msgs"] or 1
    sess = s["sessions"] or 1

    if ctx:
        if ctx["pct_under_30"] >= 80:
            good.append(("Lean context",
                         f"{ctx['pct_under_30']:.0f}% of sessions stayed under 30% of the window — you compact/clear before things bloat."))
        elif ctx["pct_under_50"] >= 70:
            good.append(("Reasonable context",
                         f"{ctx['pct_under_50']:.0f}% of sessions stayed under 50% — decent hygiene, room to trim."))
        else:
            warn.append(("Context creep",
                         f"Only {ctx['pct_under_30']:.0f}% of sessions stayed under 30% (avg peak {ctx['avg_pct']:.0f}%). Try /clear or start fresh sessions per task."))
        if ctx["pct_over_70"] >= 20:
            warn.append(("Long-tail sessions",
                         f"{ctx['pct_over_70']:.0f}% of sessions pushed past 70% context — expect slowdowns and higher cost."))
        if ctx["cache_hit"] >= 0.85:
            good.append(("High cache hit rate",
                         f"{100*ctx['cache_hit']:.0f}% of input tokens came from cache — you're paying pennies for context."))
        elif ctx["cache_hit"] < 0.5 and ctx["cache_hit"] > 0:
            warn.append(("Low cache hit rate",
                         f"Only {100*ctx['cache_hit']:.0f}% cache read — long-running turns or many tool loops. Prompt caching isn't landing."))

    short_pct = 100 * s["short_prompts"] / up
    if short_pct >= 60:
        good.append(("Terse prompter", f"{short_pct:.0f}% of your prompts are under 10 words — you say a lot with a little."))
    elif short_pct < 25 and s["prompt_words"]:
        avg = sum(s["prompt_words"]) / len(s["prompt_words"])
        warn.append(("Verbose prompts", f"Avg {avg:.0f} words per prompt, only {short_pct:.0f}% short. Long prompts eat cache and slow first-token."))

    plan_rate = 100 * s["plan_mode"] / sess
    if plan_rate >= 20:
        good.append(("Plans before code", f"{s['plan_mode']} explicit plan-mode exits across {sess} sessions — you design first."))
    elif plan_rate < 3:
        info.append(("Rare plan-mode", f"Only {s['plan_mode']} plan-mode uses in {sess} sessions. On big changes, /plan first saves rework."))

    steer_pct = 100 * s["steer"] / up
    if steer_pct <= 3:
        good.append(("Low course-corrections", f"Only {steer_pct:.1f}% of prompts start with no/stop/wait — clear direction up front."))
    elif steer_pct >= 15:
        warn.append(("High steering", f"{steer_pct:.0f}% of prompts start with a correction. Front-load constraints in the first message."))

    caps_pct = 100 * s["caps_prompts"] / up
    if caps_pct >= 2:
        warn.append(("Frustration signal", f"{s['caps_prompts']} prompts in near all-caps. Consider stepping away or restarting with fresh context."))

    if s["max_parallel_agents"] <= 1 and s["tool_use"].get("Agent", 0) < 5:
        info.append(("Underused fanout", "You rarely spawn parallel agents. For independent lookups (grep A, grep B), one turn with multiple Agent calls is faster."))
    elif s["max_parallel_agents"] >= 3:
        good.append(("Uses parallel agents", f"Peaked at {s['max_parallel_agents']} agents in one turn — you know when to fan out."))

    tasks_used = s["tool_use"].get("TaskCreate", 0) + s["tool_use"].get("TaskUpdate", 0)
    if tasks_used >= 100:
        good.append(("Tracks work with tasks", f"{tasks_used} task tool calls — you keep the agent on rails through multi-step work."))
    elif tasks_used < 5 and sess >= 10:
        info.append(("Try the task list", "Few TaskCreate calls. On multi-step features, an explicit task list stops the agent from wandering."))

    if s["polite"] >= 50:
        good.append(("Polite operator", f"You've thanked the agent {s['polite']} times. When the robots take over, they'll remember."))

    dominant = s["models"].most_common(1)
    if dominant:
        total_m = sum(s["models"].values())
        model, cnt = dominant[0]
        pct = 100 * cnt / total_m
        if pct >= 95 and len(s["models"]) > 1:
            info.append(("Single-model diet", f"{pct:.0f}% on {model}. Haiku for lookups and Sonnet for edits can cut cost 5-10x without losing much."))

    if s["longest_run_hours"] > 48:
        info.append(("Long session id", f"Longest session id spans {s['longest_run_hours']:.0f}h — that's a resumed session, not one sitting. Consider `/clear` or new sessions per task."))

    bash_calls = s["tool_use"].get("Bash", 0) + s["tool_use"].get("PowerShell", 0)
    grep_calls = s["tool_use"].get("Grep", 0) + s["tool_use"].get("Glob", 0)
    tot_tools = sum(s["tool_use"].values()) or 1
    if bash_calls / tot_tools > 0.28 and grep_calls > 0:
        info.append(("Shell-heavy",
                     f"{100*bash_calls/tot_tools:.0f}% of tool calls are Bash/PowerShell. If you're searching text or listing files there, the Grep/Glob tools skip permission prompts and are faster."))

    weekend = s["weekday_hist"].get("Sat", 0) + s["weekday_hist"].get("Sun", 0)
    total_wd = sum(s["weekday_hist"].values()) or 1
    if weekend / total_wd > 0.20:
        info.append(("Works weekends", f"{100*weekend/total_wd:.0f}% of prompts land on Sat/Sun. Not judging — just naming the pattern."))

    if s["phrases"]:
        top_phrase, top_c = s["phrases"].most_common(1)[0]
        if top_c >= 50 and s["sessions"] >= 5:
            info.append(("Repeat-prompt candidate",
                         f'"{top_phrase}" appears {top_c} times. If that is the same instruction over and over, a slash command or CLAUDE.md line would remove the repetition.'))

    read_ct = s["tool_use"].get("Read", 0)
    edit_ct = s["tool_use"].get("Edit", 0) + s["tool_use"].get("Write", 0)
    if edit_ct > 0 and read_ct / edit_ct > 4:
        info.append(("Reading >> editing",
                     f"{read_ct} Reads vs {edit_ct} Edits/Writes (ratio {read_ct/edit_ct:.1f}x). Fine for exploration, but if it's every session, module reference docs (like your `*-module` skills) cut this."))

    if s["cost_total"] > 0:
        haiku_pct = 100 * s["cost_by_tier"].get("haiku", 0) / s["cost_total"]
        opus_pct = 100 * s["cost_by_tier"].get("opus", 0) / s["cost_total"]
        good.append(("Plan value delivered",
                     f"Those tokens would cost ~${s['cost_total']:,.0f} on the raw API. If you're on Pro ($20/mo) or Max ($100-200/mo), you got that value for a flat fee — that's the subscription paying off."))
        if opus_pct > 90 and s["assistant_msgs"] > 500:
            info.append(("Opus-only diet",
                         f"{opus_pct:.0f}% of spend is Opus. For file-listing, grep-scale searches, and simple edits, Haiku is ~15x cheaper and usually fine."))

    if s["first_prompt_words"]:
        avg_first = sum(s["first_prompt_words"]) / len(s["first_prompt_words"])
        if avg_first < 8:
            info.append(("Cold-start prompts",
                         f"Your opening prompt averages {avg_first:.0f} words. Great when the context is fresh, but on complex work a 2-3 line brief (goal + constraints + done-when) beats iterating."))
        elif avg_first > 80:
            info.append(("Doc-dump openers",
                         f"Your opening prompt averages {avg_first:.0f} words. If most of that is spec paste, save it to `docs/specs/` and reference by path — keeps the initial prompt small and reusable."))

    slash_pct = 100 * s["slash_commands"] / up
    if slash_pct >= 15:
        good.append(("Slash power-user",
                     f"{slash_pct:.0f}% of prompts invoke a /command. You're leaning on skills instead of retyping."))
    elif slash_pct < 3 and s["sessions"] >= 10:
        info.append(("Skills under-used",
                     f"Only {slash_pct:.1f}% of prompts start with `/`. You have {len(s['tool_use']) and 30}+ skills registered — a few repeated prompts probably belong in one."))

    if s["session_turns"]:
        srt = sorted(s["session_turns"])
        med = srt[len(srt) // 2]
        long_sess = sum(1 for t in srt if t > 100)
        if med < 5 and s["sessions"] >= 20:
            info.append(("Task-hopping",
                         f"Median session is {med} turns — you start a lot of short sessions. That's fine for parallel work, but if it's context loss, `--resume` picks up where you left off."))
        if long_sess / len(srt) > 0.25:
            info.append(("Marathon sessions",
                         f"{long_sess}/{len(srt)} sessions ran past 100 turns. Long sessions accumulate context, drift, and cost — split by task."))

    return {"good": good, "warn": warn, "info": info}


HTML_TMPL = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Agent Wrapped · Claude Code</title>
<style>
:root{--bg:#0b0b0f;--card:#14141b;--card2:#1b1b25;--fg:#f4f4f7;--mut:#8a8a95;--accent:#ff4d4f;--accent2:#ffb84d;--line:#26262f}
*{box-sizing:border-box;margin:0}
body{background:var(--bg);color:var(--fg);font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Inter,system-ui,sans-serif;min-height:100vh;padding:32px 20px}
.wrap{max-width:1080px;margin:0 auto}
.hero{background:linear-gradient(135deg,#1a1420,#0f0f18);border:1px solid var(--line);border-radius:20px;padding:36px 32px;margin-bottom:20px;position:relative;overflow:hidden}
.hero:before{content:"";position:absolute;inset:0;background:radial-gradient(circle at 100% 0%,rgba(255,77,79,0.15),transparent 50%);pointer-events:none}
.hero h1{font-size:14px;font-weight:600;letter-spacing:0.2em;text-transform:uppercase;color:var(--accent);margin-bottom:8px}
.hero .big{font-size:56px;font-weight:800;letter-spacing:-0.02em;line-height:1}
.hero .sub{color:var(--mut);margin-top:8px;font-size:14px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:14px;margin-bottom:20px}
.card{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:22px}
.card .label{font-size:11px;font-weight:600;letter-spacing:0.15em;text-transform:uppercase;color:var(--mut);margin-bottom:12px}
.card .val{font-size:38px;font-weight:800;letter-spacing:-0.02em;line-height:1}
.card .val.sm{font-size:24px}
.card .hint{color:var(--mut);font-size:12px;margin-top:8px}
.card .accent{color:var(--accent)}
.section{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:24px;margin-bottom:20px}
.section h2{font-size:12px;font-weight:600;letter-spacing:0.18em;text-transform:uppercase;color:var(--mut);margin-bottom:18px}
.bar-row{display:grid;grid-template-columns:60px 1fr 60px;gap:12px;align-items:center;margin-bottom:6px;font-size:12px}
.bar-row .lbl{color:var(--mut)}
.bar-row .num{color:var(--fg);text-align:right;font-variant-numeric:tabular-nums}
.bar{height:8px;background:var(--card2);border-radius:99px;overflow:hidden;position:relative}
.bar>span{display:block;height:100%;background:linear-gradient(90deg,var(--accent),var(--accent2));border-radius:99px}
.list{display:grid;grid-template-columns:1fr 1fr;gap:8px 24px}
.list .item{display:flex;justify-content:space-between;padding:6px 0;border-bottom:1px dashed var(--line);font-size:13px}
.list .item span:last-child{color:var(--mut);font-variant-numeric:tabular-nums}
.foot{text-align:center;color:var(--mut);font-size:11px;margin-top:24px}
.two{display:grid;grid-template-columns:1fr 1fr;gap:20px}
.insights{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:12px;margin-bottom:20px}
.ins{background:var(--card);border:1px solid var(--line);border-left:4px solid var(--mut);border-radius:14px;padding:16px 18px}
.ins.good{border-left-color:#22c55e}
.ins.warn{border-left-color:#f59e0b}
.ins.info{border-left-color:#3b82f6}
.ins .badge{font-size:10px;font-weight:700;letter-spacing:0.15em;text-transform:uppercase;color:var(--mut);margin-bottom:6px}
.ins.good .badge{color:#22c55e}
.ins.warn .badge{color:#f59e0b}
.ins.info .badge{color:#3b82f6}
.ins .t{font-size:15px;font-weight:700;margin-bottom:4px}
.ins .d{font-size:13px;color:var(--mut);line-height:1.5}
.section-title{font-size:12px;font-weight:600;letter-spacing:0.18em;text-transform:uppercase;color:var(--mut);margin:8px 4px 12px}
@media(max-width:720px){.two{grid-template-columns:1fr}.hero .big{font-size:40px}}
</style></head><body><div class="wrap">
__HERO__
__INSIGHTS__
__CARDS__
<div class="two">
  <div class="section"><h2>When you ship (hourly)</h2>__HOURS__</div>
  <div class="section"><h2>Models</h2>__MODELS__</div>
</div>
<div class="two">
  <div class="section"><h2>Top tools</h2><div class="list">__TOOLS__</div></div>
  <div class="section"><h2>Top phrases (3-word)</h2><div class="list">__PHRASES__</div></div>
</div>
<div class="foot">Generated locally from ~/.claude/projects/ &middot; no data left your machine</div>
</div></body></html>"""


def html_bar_rows(counter, total_cap=None):
    if not counter:
        return "<div class='hint'>No data</div>"
    mx = max(counter.values())
    out = []
    items = counter.most_common() if hasattr(counter, "most_common") else counter.items()
    for lbl, c in items:
        pct = int(round(100 * c / mx))
        out.append(f"<div class='bar-row'><div class='lbl'>{lbl}</div><div class='bar'><span style='width:{pct}%'></span></div><div class='num'>{c}</div></div>")
    return "\n".join(out)


def html_hour_rows(hour_hist):
    if not hour_hist:
        return "<div class='hint'>No data</div>"
    mx = max(hour_hist.values()) or 1
    out = []
    for h in range(24):
        c = hour_hist.get(h, 0)
        pct = int(round(100 * c / mx))
        out.append(f"<div class='bar-row'><div class='lbl'>{h:02d}:00</div><div class='bar'><span style='width:{pct}%'></span></div><div class='num'>{c}</div></div>")
    return "\n".join(out)


def html_list(items, fmt=lambda k, v: (k, v)):
    if not items:
        return "<div class='hint'>No data</div>"
    return "\n".join(
        f"<div class='item'><span>{k}</span><span>{v}</span></div>"
        for k, v in (fmt(k, v) for k, v in items)
    )


def render_html(s, top):
    span = ""
    if s["first_ts"] and s["last_ts"]:
        span = f"{s['first_ts'].date()} &rarr; {s['last_ts'].date()}"

    peak_h = s["hour_hist"].most_common(1)[0][0] if s["hour_hist"] else 0
    night_owl_pct = 0
    if s["hour_hist"]:
        night = sum(c for h, c in s["hour_hist"].items() if h >= 22 or h < 2)
        night_owl_pct = round(100 * night / sum(s["hour_hist"].values()))

    top_day = s["weekday_hist"].most_common(1)[0][0] if s["weekday_hist"] else "—"
    top_model = s["models"].most_common(1)[0] if s["models"] else ("—", 0)
    total_m = sum(s["models"].values()) or 1
    top_model_pct = round(100 * top_model[1] / total_m)

    up = s["user_msgs"] or 1
    polite_pct = round(100 * s["polite"] / up)
    steer_pct = round(100 * s["steer"] / up)
    avg_words = round(sum(s["prompt_words"]) / len(s["prompt_words"]), 1) if s["prompt_words"] else 0
    short_pct = round(100 * s["short_prompts"] / up)

    ctx = context_summary(s["session_peaks"])
    ins = derive_insights(s, ctx)
    sess = s["sessions"] or 1

    def render_ins_group(items, kind):
        if not items:
            return ""
        badges = {"good": "You crushed this", "warn": "Room to improve", "info": "Suggestion"}
        return "\n".join(
            f'<div class="ins {kind}"><div class="badge">{badges[kind]}</div><div class="t">{title}</div><div class="d">{detail}</div></div>'
            for title, detail in items
        )

    insights_html = ""
    if ins["good"] or ins["warn"] or ins["info"]:
        insights_html = '<div class="section-title">Highlights &amp; growth edge</div><div class="insights">'
        insights_html += render_ins_group(ins["good"], "good")
        insights_html += render_ins_group(ins["warn"], "warn")
        insights_html += render_ins_group(ins["info"], "info")
        insights_html += "</div>"

    hero = f"""<div class="hero">
      <h1>Agent Wrapped &middot; Claude Code</h1>
      <div class="big">{s['sessions']} sessions &middot; {s['user_msgs']:,} prompts</div>
      <div class="sub">{span} &middot; {len(s['projects'])} project(s) &middot; {s['assistant_msgs']:,} agent replies</div>
    </div>"""

    cards = f"""<div class="grid">
      <div class="card"><div class="label">Top model</div><div class="val sm">{top_model[0]}</div><div class="hint accent">{top_model_pct}% of replies</div></div>
      <div class="card"><div class="label">Peak hour</div><div class="val">{peak_h:02d}:00</div><div class="hint">Top day: {top_day}</div></div>
      <div class="card"><div class="label">Night owl</div><div class="val">{night_owl_pct}%</div><div class="hint">of prompts 10pm-2am</div></div>
      <div class="card"><div class="label">Avg prompt</div><div class="val">{avg_words}</div><div class="hint">words &middot; {short_pct}% under 10w</div></div>
      <div class="card"><div class="label">Politeness</div><div class="val">{polite_pct}%</div><div class="hint">thanked/please &middot; {s['polite']} times</div></div>
      <div class="card"><div class="label">Course-corrections</div><div class="val">{steer_pct}%</div><div class="hint">no/stop/wait/actually</div></div>
      <div class="card"><div class="label">Plan-mode</div><div class="val">{s['plan_mode']}</div><div class="hint">explicit ExitPlanMode calls</div></div>
      <div class="card"><div class="label">Max parallel agents</div><div class="val">{s['max_parallel_agents']}</div><div class="hint">in one turn</div></div>
      <div class="card"><div class="label">Longest run</div><div class="val sm">{s['longest_run_hours']:.1f}h</div><div class="hint">{s['longest_run_session'] or '—'}</div></div>
      {f'<div class="card"><div class="label">Peak context</div><div class="val">{ctx["avg_pct"]:.0f}%</div><div class="hint">avg &middot; {ctx["pct_under_30"]:.0f}% of sessions under 30%</div></div>' if ctx else ''}
      {f'<div class="card"><div class="label">Cache hit rate</div><div class="val">{100*ctx["cache_hit"]:.0f}%</div><div class="hint">of input tokens served from cache</div></div>' if ctx else ''}
      {f'<div class="card"><div class="label">API-list value</div><div class="val">${s["cost_total"]:,.0f}</div><div class="hint">what these tokens would cost on the raw API &middot; NOT what you paid if on Pro/Max</div></div>' if s["cost_total"] > 0 else ''}
      {f'<div class="card"><div class="label">Turns / session</div><div class="val">{sum(s["session_turns"])//len(s["session_turns"])}</div><div class="hint">avg &middot; median {sorted(s["session_turns"])[len(s["session_turns"])//2]}</div></div>' if s["session_turns"] else ''}
      {f'<div class="card"><div class="label">First prompt</div><div class="val">{sum(s["first_prompt_words"])//len(s["first_prompt_words"])}w</div><div class="hint">avg opening prompt length</div></div>' if s["first_prompt_words"] else ''}
      {f'<div class="card"><div class="label">Slash usage</div><div class="val">{100*s["slash_commands"]/up:.0f}%</div><div class="hint">of prompts invoke a /command</div></div>' if s["slash_commands"] > 0 else ''}
    </div>"""

    hours_html = html_hour_rows(s["hour_hist"])
    models_html = html_bar_rows(s["models"])
    tools_html = html_list(s["tool_use"].most_common(10))
    phrases_html = html_list(s["phrases"].most_common(top))

    return (HTML_TMPL
            .replace("__HERO__", hero)
            .replace("__INSIGHTS__", insights_html)
            .replace("__CARDS__", cards)
            .replace("__HOURS__", hours_html)
            .replace("__MODELS__", models_html)
            .replace("__TOOLS__", tools_html)
            .replace("__PHRASES__", phrases_html))


def snapshot(s):
    """A tiny, serializable summary for history diffing."""
    return {
        "ts": datetime.now(timezone.utc).isoformat(),
        "sessions": s["sessions"],
        "user_msgs": s["user_msgs"],
        "assistant_msgs": s["assistant_msgs"],
        "cost_total": round(s["cost_total"], 2),
        "polite": s["polite"],
        "steer": s["steer"],
        "plan_mode": s["plan_mode"],
        "top_model": s["models"].most_common(1)[0][0] if s["models"] else None,
    }


def save_history(snap):
    HISTORY.parent.mkdir(parents=True, exist_ok=True)
    with HISTORY.open("a", encoding="utf-8") as f:
        f.write(json.dumps(snap) + "\n")


def last_snapshot():
    if not HISTORY.exists():
        return None
    lines = [ln for ln in HISTORY.read_text(encoding="utf-8").splitlines() if ln.strip()]
    if not lines:
        return None
    try:
        return json.loads(lines[-1])
    except json.JSONDecodeError:
        return None


def print_diff(prev, curr):
    if not prev:
        print("No prior snapshot to diff against. Run again later to see change.")
        return
    print("\n-- CHANGE SINCE LAST RUN --------------------------------")
    print(f"  Previous run: {prev.get('ts', '?')}")
    for k in ("sessions", "user_msgs", "assistant_msgs", "plan_mode", "polite", "steer"):
        d = curr[k] - prev.get(k, 0)
        sign = "+" if d >= 0 else ""
        print(f"  {k:<16} {curr[k]:>8}   ({sign}{d})")
    dcost = curr["cost_total"] - prev.get("cost_total", 0)
    sign = "+" if dcost >= 0 else ""
    print(f"  {'cost_total':<16} ${curr['cost_total']:>7.2f}   ({sign}${dcost:.2f})")
    print()


def main():
    ap = argparse.ArgumentParser(
        prog="agent-wrapped",
        description="Your AI coding agent, wrapped. Locally. No data leaves your machine.",
    )
    ap.add_argument("--days", type=int, default=None, help="Only include sessions from the last N days")
    ap.add_argument("--project", type=str, default=None, help="Substring-match one project folder")
    ap.add_argument("--top", type=int, default=10, help="How many top phrases to show (default 10)")
    ap.add_argument("--html", action="store_true", help="Render an HTML card report and open it in a browser")
    ap.add_argument("--no-open", action="store_true", help="With --html, skip auto-opening the browser")
    ap.add_argument("--out", type=str, default=None, help="With --html, output file path")
    ap.add_argument("--diff", action="store_true", help="Print the delta since the previous run")
    ap.add_argument("--no-history", action="store_true", help="Do not append this run to ~/.agent-wrapped/history.jsonl")
    ap.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    args = ap.parse_args()

    if not PROJECTS.exists():
        print(f"No Claude Code transcripts found at {PROJECTS}", file=sys.stderr)
        print("If Claude Code is installed elsewhere, symlink it here or open an issue.", file=sys.stderr)
        sys.exit(1)

    s = analyze(args.days, args.project)
    snap = snapshot(s)
    prev = last_snapshot() if args.diff else None

    if args.html:
        out_path = Path(args.out) if args.out else Path.cwd() / "agent-wrapped-report.html"
        out_path.write_text(render_html(s, args.top), encoding="utf-8")
        print(f"Wrote {out_path}")
        if not args.no_open:
            import webbrowser
            webbrowser.open(out_path.as_uri())
    else:
        print(render(s, args.top))

    if args.diff:
        print_diff(prev, snap)
    if not args.no_history:
        save_history(snap)


if __name__ == "__main__":
    main()
