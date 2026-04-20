Pre-flight clarify gate. Invoked BEFORE `/build`, and may be invoked standalone at any time.

When run, instruct the agent on the next READY story to:
1. Read the story file plus docs/HANDOFF.md
2. Output its Pre-Flight block (Assumptions / Open Questions / Simplicity Check / Surgical-Change Test / TDD Plan)
3. STOP — do NOT write any code, tests, or files
4. Wait for the user to either:
   - Answer the Open Questions
   - Correct wrong Assumptions
   - Accept the plan as-is and explicitly approve proceeding

The agent must not produce a single line of implementation output before the user approves the Pre-Flight block.

Use `/think` whenever a story feels ambiguous, whenever the scrum-master's success criteria look imperative, or whenever an agent has previously jumped ahead and produced work you had to reject. It is the explicit Karpathy "Think Before Coding" gate.

This command does NOT replace `/start` — it is a complement for stories that are already READY.
