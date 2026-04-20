Locally simulate the D14 validation gates against a candidate hieradata edit.

Run: `python scripts/validate_local.py --env <alpin|dostoneu|dani> --file <path> --diff <path-to-diff>`

Executes the five gates in order:
  1. yaml_parse (ruamel)
  2. yamllint
  3. key_shape (against known_keys)
  4. byte_diff_drift
  5. secret_leak

Prints pass/fail + canonical error code per gate. Stops at the first failure, matching server behaviour.

Use this before pushing an MR so you see exactly what the server-side gate would reject.
