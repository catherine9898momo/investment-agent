# Company Research

This directory stores company-level research packs and monitoring outputs.

Each company should keep a stable folder by ticker:

```text
company_research/
  MU/
    thesis.md
    monitoring.yaml
    reports/
```

Suggested workflow:

1. Keep the durable thesis, anti-thesis, and falsification conditions in `thesis.md`.
2. Keep repeatable monitoring inputs and thresholds in `monitoring.yaml`.
3. Generate reports with:

```bash
python -m src.company_research.monitor MU --data-source fixture
python -m src.company_research.monitor MU --data-source live
```

`fixture` mode uses the company pack's stored facts and is safe for offline checks.
`live` mode also pulls quote, history, and news through the existing tool backends.
