Invoke frontend-dev and bff-dev **in parallel** (agent teams) on the next READY story in docs/stories/. This parallel dispatch is mandatory under CLAUDE.md Principle 5 — do not serialize the two lanes unless the story's Cross-Cutting Concerns table names a dependency that requires it.

Both agents must keep docs/HANDOFF.md updated on cross-cutting changes. If a lane finishes before the other, it should start its local validation commands (`mypy`, `pytest`, `tsc --noEmit`, `npm test`) while the other lane is still implementing — do not idle.

When multiple READY stories exist with no cross-dependency (verify against the scrum-master's dependency graph), dispatch N agent pairs concurrently (one pair per story) up to host capacity.
