# Screenshots

The images referenced in the top-level [README](../README.md).

## Files

| File | Section |
|---|---|
| `report-hero.png` | Hero + Highlights &amp; growth-edge insight cards |
| `report-cards.png` | Full stat-card grid (models, timing, style, cost, cache) |
| `report-tables.png` | Top tools + top three-word phrases |

## Regenerating

Run the tool, open the browser, and re-capture each section.

```bash
agent-wrapped --html --days 30
```

Tips:

- Use a **dark browser theme** &mdash; matches the HTML report.
- Zoom to **90%** before capturing so more fits without losing legibility.
- Crop each PNG to ~1600&times;900 (landscape) for the hero + cards.
- Windows: `Win + Shift + S` or F12 dev-tools "Capture full size screenshot".
- macOS: `Cmd + Shift + 4`.

After replacing a PNG, `git add screenshots/<file>.png && git commit -m "docs: refresh screenshot"`.
