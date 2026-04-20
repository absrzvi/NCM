Read-only prime for the frontend-dev agent. Read these files and summarise:
- frontend/src/App.tsx
- frontend/src/auth/KeycloakProvider.tsx
- frontend/src/hooks/ (one-line summary per hook)
- frontend/src/stores/ (one-line summary per store)
- frontend/src/types/ (one-line summary per module)
- docs/API_CONTRACTS.md
- docs/HANDOFF.md

Output a compact summary:
- Views that exist (map to the five module routes)
- TypeScript types defined and which BFF endpoints they map to
- Zustand stores and what state they manage
- Any gaps: BFF endpoints in API_CONTRACTS.md that have no corresponding hook or type
- Open items from HANDOFF.md relevant to frontend work

Do not read every component file. This prime is intentionally scoped to types, stores, hooks, and auth.
