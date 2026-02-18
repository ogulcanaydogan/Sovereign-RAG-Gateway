# PGVector Ranking Eval Report

Status: **PASS**

- Run at: `2026-02-18T05:47:04.607462+00:00`
- Samples: `3`
- Recall@3: `1.0`
- MRR: `1.0`
- Threshold: `0.8`

| id | hit | rank | expected | top_sources |
|---|---:|---:|---|---|
| triage-note | yes | 1 | triage-note-01.txt | triage-note-01.txt,discharge-summary-02.txt |
| discharge-summary | yes | 1 | discharge-summary-02.txt | discharge-summary-02.txt,triage-note-01.txt |
| guardrail-policy | yes | 1 | policy-guardrail-03.md | policy-guardrail-03.md |
