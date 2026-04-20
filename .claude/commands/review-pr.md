Invoke code-reviewer and security-sentinel **in parallel** (mandatory under CLAUDE.md Principle 5 — the two reviews are independent and share no mutable state).
Both must output APPROVED before the PR is merged. A CHANGES_REQUESTED from either blocks the merge; a BLOCKED from security-sentinel blocks unconditionally.
