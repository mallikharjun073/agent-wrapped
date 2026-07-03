# agent-wrapped

**Your AI coding agent, wrapped — locally. Zero data uploaded.**

`agent-wrapped` reads the session transcripts your AI coding agent already
stores on disk, and prints a Spotify-Wrapped-style report about how *you*
use it. Peak hours, top model, prompt style, plan-mode habits, top phrases,
context peaks, and the API-list value of everything you've done.

Runs in seconds. One Python file, standard library only, no dependencies,
no Docker, no account, no upload.

> **v0.1 supports Claude Code.** Codex CLI and Cursor are on the roadmap
> (they use different transcript schemas — separate PRs). See below.

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://www.python.org/downloads/)
[![No deps](https://img.shields.io/badge/dependencies-0-brightgreen)](agent_wrapped.py)
[![Local only](https://img.shields.io/badge/data-never%20leaves%20your%20machine-brightgreen)](PRIVACY.md)

---

## Why

Some tools (like Y Combinator's Paxel) do a similar job, but they upload
transcript excerpts to a third-party service to score you against other
users. That's a reasonable trade for cross-user benchmarks, but if your
prompts contain client code, credentials, spec paste, or internal URLs,
you may not want them leaving your laptop.

`agent-wrapped` gives you the same personal insight without the upload.
Your baseline is **you last week**, not strangers on the internet.

---

## Install

Pick whichever feels right.

### 1. One-shot (no install)

```bash
curl -fsSL https://raw.githubusercontent.com/mallikharjun073/agent-wrapped/main/agent_wrapped.py -o agent_wrapped.py
python agent_wrapped.py --html
```

### 2. `pipx` (recommended for regular use)

```bash
pipx install agent-wrapped
agent-wrapped --html
```

### 3. From source

```bash
git clone https://github.com/mallikharjun073/agent-wrapped.git
cd agent-wrapped
python agent_wrapped.py --html
```

Requires Python 3.9+. That's it. No pip packages to install.

---

## Usage

Print a text report to your terminal:

```bash
agent-wrapped
```

Render an HTML dashboard and open it in your browser:

```bash
agent-wrapped --html
```

Last 30 days only:

```bash
agent-wrapped --html --days 30
```

Show what changed since your last run:

```bash
agent-wrapped --diff
```

All options:

| Flag | What it does |
|---|---|
| `--html` | Render an HTML card report and open it in your browser |
| `--days N` | Only include sessions from the last N days |
| `--project SUB` | Filter to one project folder (substring match on the folder name) |
| `--top N` | How many top phrases to show (default 10) |
| `--diff` | Print the delta since the previous run |
| `--no-history` | Don't append this run to `~/.agent-wrapped/history.jsonl` |
| `--no-open` | With `--html`, don't auto-open the browser |
| `--out PATH` | With `--html`, write to a specific file |
| `--version` | Print version and exit |

---

## What you get

**Terminal:**

```
AGENT WRAPPED  ·  Claude Code
Sessions           111   across 3 project(s)  (2026-05-28 → 2026-07-03)
Your prompts      2292
Agent replies    43780
Avg prompt       366.9 words   short (<10w): 35%

-- MODELS --
  claude-opus-4-7               82.4%  ####################
  claude-opus-4-8               17.5%  ####................
```

**HTML report:** hero + a grid of cards (Top model, Peak hour, Night owl %,
Plan-mode, Politeness, Course-corrections, Max parallel agents, Longest run,
Peak context %, Cache hit rate, API-list value, Turns / session, First
prompt length, Slash usage), followed by an insights section that calls out
what you're doing well and where you can improve — and finally the hourly
histogram, model split, top tools, and top phrases.

**Insights** are rule-based and specific. Examples that fire on real data:

- *"High cache hit rate: 95% of input tokens came from cache — you're paying pennies for context."*
- *"Context creep: only 8% of sessions stayed under 30% of the window. Try /clear between tasks."*
- *"Repeat-prompt candidate: `frontend src app` appears 1,597 times. If that's the same instruction, a slash command would remove it."*
- *"Plan value delivered: those tokens would cost ~$28,878 on the raw API. If you're on Pro/Max, that's the subscription paying off."*

---

## Privacy

`agent-wrapped` reads exactly one thing: your local Claude Code transcript
folder (`~/.claude/projects/`). It writes exactly two things:

1. Your HTML report (path you choose)
2. `~/.agent-wrapped/history.jsonl` — one-line snapshots for `--diff` (opt-out with `--no-history`)

It makes **zero network calls**. No fonts, no CDNs, no telemetry, no beacons.
The generated HTML is fully offline. Grep the source for `urllib|requests|http|socket` and you'll find nothing.

Full breakdown: [PRIVACY.md](PRIVACY.md).

---

## How it works

Claude Code writes every conversation as a `.jsonl` file under
`~/.claude/projects/<project-slug>/<session-id>.jsonl`. Each line is a
JSON record: user prompts, assistant responses, tool calls, token usage,
timestamps. `agent-wrapped` streams those files line-by-line and tallies:

- Per-model output & input token totals → cost estimate (list-price)
- Per-turn input+cache tokens → context peak per session
- User-message word counts, first-word patterns, /slash prefixes
- Assistant-message `tool_use` blocks → tool call frequency, `Agent`
  concurrency per turn, `ExitPlanMode` count
- Timestamps → hour and weekday histograms

Then a small rule engine (`derive_insights` in `agent_wrapped.py`) produces
green / amber / blue callouts based on thresholds. Read it — it's ~100 lines.

---

## Comparison

|  | agent-wrapped | Paxel (YC) |
|---|---|---|
| Data upload | Never | Transcript excerpts sent to Claude/GPT + scored JSON to YC |
| Install | `pipx install` or `curl` | Docker + account + sign-in |
| Runtime | Seconds | 15–30 minutes |
| Compare to other users | No (by design) | Yes |
| Compare to your last week | Yes (`--diff`) | No |
| Multi-tool | Claude Code (v0.1) · Codex/Cursor on roadmap | Claude + Codex + Cursor |
| Source | 1 Python file, ~700 lines | Closed |

Both tools are useful. If you want a comparative dataset, use Paxel. If you
want your prompts to stay on your laptop, use this.

---

## Roadmap

- [ ] **Codex CLI parser** — `~/.codex/sessions/**/*.jsonl` uses a different schema (`agent_message`, `input_text`, `event_msg`, `patch_apply_end` …); worth a dedicated PR.
- [ ] **Cursor parser** — chat history lives in SQLite under `workspaceStorage/`; needs schema mapping.
- [ ] `--share` — render a 1080×1350 PNG for social posts.
- [ ] Weekday radial chart.
- [ ] Optional archetype classification (fully local, no LLM call).
- [ ] Per-project drill-down (`--split-by project`).

PRs welcome. Keep the "zero dependencies" bar.

---

## Contributing

1. Fork, branch, PR against `main`.
2. Keep the module single-file and stdlib-only.
3. If you add a new parser, put it in the same file behind a small
   `parse_<toolname>()` function that yields the same normalized event
   shape the current analyzer consumes.
4. No new network calls, no telemetry, no analytics — that's the whole product.

## License

[MIT](LICENSE). Use it, fork it, ship it.

## Credits

Inspired by (and a friendly response to)
[Paxel](https://paxel.ycombinator.com/) — the same idea, minus the upload.
