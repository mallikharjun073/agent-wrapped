# Privacy

**agent-wrapped is 100% local. No data ever leaves your machine.**

## What it reads

- `~/.claude/projects/**/*.jsonl` — your Claude Code session transcripts, stored locally by Claude Code itself.

That's it. Nothing else on disk. (Codex CLI and Cursor readers are on the roadmap; they will follow the same local-only rule.)

## What it writes

- Whatever path you pass to `--out` (default: `./agent-wrapped-report.html`) — a self-contained HTML file with your stats.
- `~/.agent-wrapped/history.jsonl` — a one-line snapshot per run for the `--diff` feature. Pass `--no-history` to skip this.

## What it sends over the network

**Nothing.** There are zero network calls in the source. Grep for `urllib`, `requests`, `http`, `socket`, `urlopen` — you will not find any.

The generated HTML report is a fully offline file. No fonts, no CDN, no analytics beacons.

## What runs

A single Python file, ~700 lines, standard-library only. You can read the whole thing in one sitting.

## Comparison to hosted alternatives

Some hosted "coding wrapped" tools (e.g. Paxel by Y Combinator) send transcript excerpts to third-party LLMs (Claude, GPT) for scoring and archetype classification, plus a summary JSON to their servers. That's a reasonable trade if you want cross-user comparisons — but if your prompts contain client code, credentials, spec paste, or internal URLs, that data is leaving your machine.

agent-wrapped does not offer comparisons to other users. It compares you to *you last week* via the local history file. That's the trade.

## Verifying the claim

```bash
# grep the source for anything network-shaped
grep -nE "urllib|requests|http\.|socket|urlopen|fetch|post\(" agent_wrapped.py
```

Empty output. If you want to be extra paranoid, run behind a firewall block for the Python process — nothing will break.
