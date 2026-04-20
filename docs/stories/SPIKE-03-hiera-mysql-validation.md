# Spike: [SPIKE-03] hiera_mysql Opaque Rendering Validation
Status: READY
D-decisions touched: D10 (hiera.yaml parsing — phase-2 extension for dani fleet)

## Why (from PRD)
The dani fleet (phase-2) uses a 9-layer hierarchy including the `hiera_mysql` lookup plugin. D10 architecture proposes rendering `hiera_mysql`-routed keys as opaque badges with the message "value resolved at runtime from Puppet DB — MVP cannot show the effective value". This spike validates that approach with project engineers and scopes the phase-2 DB-read path.

## Assumptions
- dani fleet onboarding is phase-2, not MVP day-one.
- This spike does NOT block alpin or dostoneu MVP stories.
- At least one project engineer (PE) familiar with dani fleet hieradata must confirm the opaque rendering is acceptable.
- If PEs require read-only DB value display in phase-2, the spike will scope what's needed (connection details, query shape, secret handling) but NOT implement it.

## What to Investigate
1. Present the opaque rendering proposal to at least one PE:
   - `hiera_mysql`-routed keys display an `external_db` badge in the PolicyTree
   - Tooltip or info panel: "This parameter's value is resolved at runtime from the Puppet MySQL DB. The NMS+ Config MVP cannot show the effective value. To view or edit, connect to the Puppet DB directly."
   - The key is NOT editable through NMS+ in MVP
2. Capture PE feedback: is this acceptable for phase-2 dani rollout?
3. If PEs require read-only value display in phase-2, document:
   - Puppet MySQL DB connection details (host, port, credentials storage)
   - Query shape to resolve a key (SQL statement, parameters)
   - Secret handling (how DB credentials are stored, rotated, scoped)
   - Estimated effort to add a `puppet_mysql_client.py` in phase-2

Produce a phase-2 scoping note in `docs/stories/PHASE2-dani-hiera-mysql.md`:
```markdown
# Phase-2: dani Fleet + hiera_mysql Read Path
Status: SCOPING (not a story — placeholder for phase-2)
D-decisions touched: D10 (extended)

## PE Feedback (from SPIKE-03)
- [Date] [PE name]: [summary of feedback on opaque rendering]
- Acceptable for phase-2? [yes/no]
- Read-only value display required? [yes/no]

## If Read-Only Display Required
- Puppet MySQL DB endpoint: [host:port]
- Credentials: [where stored — K8s Secret? host file?]
- Query shape: [SQL statement with parameters]
- Secret rotation: [how often, who owns]
- Estimated effort: [X story points or days]
- Security review required: [yes — new downstream with write-capable creds?]

## Recommendation
[One sentence: proceed with opaque rendering in phase-2, or prioritise read-only client?]
```

## Pass Criteria
- At least one PE has reviewed and confirmed the opaque rendering approach is acceptable for phase-2.
- Scoping note committed to `docs/stories/PHASE2-dani-hiera-mysql.md`.
- If PEs require read-only display, all required details (DB endpoint, query, credentials) are documented.

## Fail Criteria
- None — this spike is investigative only and does not block MVP. Even if PEs reject opaque rendering, the dani fleet is phase-2, so alpin/dostoneu MVP proceeds.

## Affected Files
- docs/stories/PHASE2-dani-hiera-mysql.md → create (new file, scoping note)
- docs/stories/SPIKE-03-hiera-mysql-validation.md → this file (deliverable)

## Deliverables
1. PE interview notes appended to this file under "## PE Feedback" section
2. `docs/stories/PHASE2-dani-hiera-mysql.md` committed with phase-2 scoping notes
3. Pass verdict (this spike cannot fail — it's investigative)

## PE Feedback
[To be filled by the agent executing this spike — capture PE name, date, and verbatim feedback]

## Verdict
PASS (investigative — no failure mode)

## Blocks
- None — this spike does not block MVP. dani fleet onboarding is phase-2.

## Acceptance Criteria
- [ ] Given at least one PE is available, when the opaque rendering proposal is presented, then their feedback is captured in writing
- [ ] Given PE feedback is captured, when the opaque rendering is acceptable, then the phase-2 scoping note confirms "opaque rendering approved"
- [ ] Given PE feedback requests read-only display, when the scoping note is written, then all DB connection details, query shape, and secret handling requirements are documented
- [ ] Given the scoping note is complete, when it is committed, then the phase-2 dani stories can reference it

## Definition of Done
- [ ] At least one PE interviewed (name, date, and feedback captured)
- [ ] `docs/stories/PHASE2-dani-hiera-mysql.md` committed with complete scoping notes
- [ ] This spike marked PASS (no failure mode)
