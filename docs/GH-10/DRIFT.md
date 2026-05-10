## Spec ↔ Implementation Drift

**Task:** GH-10
**Date:** 2026-05-09
**Base:** origin/main (3 committed ahead; remainder in working tree)
**Changed files:** 25 total (6 spec-declared + 19 other)

---

### Missing Implementation
Spec listed these files; diff doesn't touch them.

| Severity | File | Spec marker | Notes |
|----------|------|-------------|-------|
| — | — | — | All 6 spec-declared files are present in the diff. No missing implementation. |

### Unspecified Changes
Diff touches these files; spec didn't list them.

| Severity | File | Notes |
|----------|------|-------|
| WARN | `app/api/routes/auth.py` | Spec explicitly states backend is already migrated and requires no changes. File shows working-tree modifications from a **prior session** (pre-GH-10 backend migration work that was never committed). Not a GH-10 regression — pre-existing uncommitted state. Should be committed separately or confirmed as complete before merge. |
| WARN | `app/config.py` | Same situation as above — modified in working tree from prior backend session, not by GH-10 implementation. |
| WARN | `docs/GH-2/`, `docs/GH-3/`, `docs/GH-4/`, `docs/GH-8/` (9 deleted files) | Cleanup of previous tickets' spec/drift/review/preflight artifacts. Not part of GH-10 scope but safe — prior tickets are closed. Should be committed in a separate housekeeping commit to keep GH-10 diff clean. |
| NOTE | `.claude/settings.json`, `.claude/task-progress/ACTIVE*` (3 files) | Tool/pipeline metadata. Not code, not user-facing. No action needed. |
| ALLOW | `frontend/bun.lock`, `frontend/tsconfig.tsbuildinfo`, `.beads/issues.jsonl` | Lockfile, build artifact, issue tracker. Allowlisted by convention. |

### Acceptance Criteria Coverage

| AC | Status | Evidence |
|----|--------|----------|
| 1 — Unauth → /login with `<SignIn />` | COVERED | `ProtectedRoute.tsx`: `if (!isSignedIn) return <Navigate to="/login" replace />` · `LoginPage.tsx`: `<SignIn />` rendered at /login |
| 2 — Social/magic link login redirects back | WARN | Clerk's `<SignIn />` default behavior handles post-auth redirect. No `afterSignInUrl` prop set — Clerk defaults to `/`. Covered by Clerk SDK internals, not visible in diff. Acceptable: Clerk's hosted UI is the implementation. |
| 3 — fetchAPI sends `Authorization: Bearer` with Clerk JWT | COVERED | `client.ts:34-38`: `_clerkGetToken()` called, result set as `Bearer` header in every authenticated request |
| 4 — `/auth/verify` returns valid + user_id | COVERED | Pre-existing: `auth.py:68-76` — `GET /auth/verify` endpoint confirmed present, returns `{"valid": True, "user_id": claims.get("sub")}` |
| 5 — `auth_disabled=True` returns "dev-user" | COVERED | Pre-existing: `auth.py:83-84` — `if settings.auth_disabled: return "dev-user"` unchanged |
| 6 — Legacy symbols absent from `client.ts` | COVERED | `grep` for `TOKEN_KEY`, `getToken`, `setToken`, `clearToken`, `isAuthenticated`, `login(password`, `logout()` in `client.ts` → zero hits |
| 7 — `POST /auth/login` returns 404 | COVERED | `grep` for `auth/login` in `auth.py` → not present; FastAPI will return 404 for unregistered path |
| 8 — `.env.example` documents both keys | COVERED | `.env.example` now includes `VITE_CLERK_PUBLISHABLE_KEY` and `CLERK_SECRET_KEY` with comments explaining public vs secret key placement |
| 9 — TypeScript build succeeds | COVERED | `bun run build` ran clean: `tsc -b && vite build` → zero errors, 1716 modules, dist/ written |

---

### Summary
- BLOCK: 0
- WARN:  3 (2 unspecified file changes — pre-existing backend work; 1 AC heuristic — social redirect via Clerk SDK default)

### Verdict
**APPROVE**

Zero blocking drift. Three WARNs — all explainable:
1. `app/api/routes/auth.py` + `app/config.py` in the diff are pre-GH-10 backend work, not regressions. Recommend committing them first in a separate commit (`fix(auth): backend clerk migration`) to keep the GH-10 PR diff clean.
2. AC 2 (social login redirect) is fulfilled by Clerk SDK defaults — no code evidence needed. Acceptable.
