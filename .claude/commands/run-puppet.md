Locally simulate the D13 safety envelope against a dev environment. NEVER against prod.

Run: `python scripts/run_puppet_local.py --env devel --certname <node> --user <your-sub> --role config-engineer`

The script executes the three envelope checks in dry-run mode:
  (1) MR merged & pipeline green for the target branch
  (2) target branch == devel or staging (refuses master/ODEG)
  (3) no drift between requested_sha and HEAD

Prints a pass/fail per check. Does NOT call Puppet Server on fail. On pass, logs a "would execute" line and stops — it does NOT actually trigger the run in local mode.

Use this during development to verify your envelope wiring before shipping a story that touches /run-force.
