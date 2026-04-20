Post-implementation overcomplication audit. Invoked on a completed branch before the formal `/review-pr` step.

When run, launch the code-reviewer agent with the narrow brief:
"Run ONLY the Simplicity First portion of the Karpathy Conformance checklist against the current branch's diff. Produce an output of the form:"

```
## /simplify report — [branch]
Diff size: [N files, M insertions, K deletions]
Senior-engineer test: PASS | FAIL
Findings (FAIL only):
- [e.g. `bff/factories/drift_record_factory.py` — single-use factory; replace with direct construction in caller]
- [e.g. `bff/routers/policies.py` — three almost-identical read handlers; collapse to one parametrised handler]
- [e.g. `frontend/src/stores/useDraft.ts` — unused actions `bulkUndo`, `exportJson`; remove — not in story AC list]
Recommended changes: [numbered list]
```

If the report is PASS, ship it. If FAIL, either simplify then re-run `/simplify`, OR justify each finding in the PR description and let `code-reviewer` adjudicate.

Does not block merges on its own — it is an advisory, cheap feedback loop.
