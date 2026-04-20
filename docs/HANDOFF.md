# Workflow Handoff

> Written by each agent at stage completion. The next agent reads this first — instead of re-reading all upstream docs.
> Keep entries minimal: only what the next agent needs that isn't already in the story file or CLAUDE.md.

---

## Current Stage
SPIKE-01 COMPLETE (PASS)

## Feature / Story in Flight
SPIKE-01 — hiera_file Plugin Inventory (`docs/stories/SPIKE-01-hiera-file-inventory.md`)

## D-decisions Touched
D10 (hiera.yaml layer parsing — static reconstruction assumption verified for alpin + dostoneu)

## Last Decision Made
`plugin_is_static: true` for both alpin and dostoneu fleets; D10 implementation is unblocked.

## What the Next Agent Must Know
- The `nomad_connect` submodule is not present in this workspace. Static verdict was derived from hiera.yaml fixture evidence (path: "hieradata/files" contains no variable interpolation). An operator with submodule access should confirm via direct Ruby source grep before D10 stories are marked fully unblocked.
- `hieradata/files/` is absent from both fixture captures — `routed_keys` lists are currently empty. After SPIKE-04 (fixture capture) runs and includes the files/ subtree, the inventory files must be updated with real routed_keys entries.
- STORY-13, STORY-31, STORY-16 are unblocked pending the SPIKE-04 caveat above.
- `bff/config/hiera_file_inventory/alpin.yaml` and `dostoneu.yaml` are now committed with `routed_keys: []` and `plugin_is_static: true`.

## Open Constraints
- Do not mark STORY-13/STORY-31/STORY-16 fully DONE until SPIKE-04 has populated hieradata/files/ and the inventory routed_keys lists have been verified complete.
- If the operator inspects nomad_connect source and finds conditional dispatch, immediately open ADR-017 and re-set SPIKE-01 to FAIL.

## Handoff Log
| Date | From | To | Summary |
|------|------|----|---------|
| 2026-04-20 | spike-agent (SPIKE-01) | next-agent | SPIKE-01 PASS: plugin_is_static=true for alpin+dostoneu; inventory files created; SPIKE-04 follow-up needed for routed_keys population |
