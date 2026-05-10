# Preflight — GH-10 feat(auth): Clerk zero-credential social login

**Date:** 2026-05-10
**Environment:** dev → prod (PR preview → main merge)
**Branch:** `feature/GH-10-clerk-zero-credential-auth`
**Executor:** Drew Schillinger
**Verifier:** Drew Schillinger
**Rollback authority:** Drew Schillinger

---

## Interview Answers

| # | Question | Answer |
|---|----------|--------|
| 1 | What are we deploying? | GH-10 — Clerk zero-credential social login. Branch `feature/GH-10-clerk-zero-credential-auth`. No PR yet. |
| 2 | Target environment? | Dev preview first (Railway PR deploy), then production on merge to main. |
| 3 | What changed? | **Frontend:** `@clerk/clerk-react@5.61.3` installed; `main.tsx` (ClerkProvider + ClerkTokenSync); `client.ts` (localStorage auth removed, initClerkAuth added, Bearer token injection); `ProtectedRoute.tsx` (useAuth guard); `LoginPage.tsx` (<SignIn /> component); `.env.example` (documented keys). **Backend (prior session, commit separately):** `app/api/routes/auth.py` (Clerk JWKS RS256 verification, require_auth); `app/config.py` (clerk_secret_key + auth_disabled fields). |
| 4 | Migration / data scripts? | None. No DB schema changes. No data migrations. |
| 5 | Config changes? | Yes — two new env vars required. See Config Checklist below. |
| 6 | Team roster? | Drew solo: executor, verifier, rollback authority. |
| 7 | Cross-team dependencies? | External: Clerk account must exist at dashboard.clerk.com with GitHub + Google social providers enabled, and production keys generated. |

---

## Script Validation

No migration or data scripts present. R1/R2/R3 gates: N/A — all pass.

---

## Config Checklist

These vars must be set before the deploy is live. Verify each:

| Var | Location | Status |
|-----|----------|--------|
| `VITE_CLERK_PUBLISHABLE_KEY` | `frontend/.env.local` (local) + Railway service env (deploy) | Must be set from Clerk dashboard → API Keys → Publishable key |
| `CLERK_SECRET_KEY` | `.env` (local) + Railway service env (deploy) — **never commit** | Must be set from Clerk dashboard → API Keys → Secret key |
| `AUTH_DISABLED` | Railway env (if present) | Must be `False` or unset in prod; `True` only for local dev without Clerk |

> `VITE_CLERK_PUBLISHABLE_KEY` is public by design — safe in Railway's plaintext env, safe in browser bundle.
> `CLERK_SECRET_KEY` is a secret — set it in Railway's secret env section, never in source control.

---

## Pre-Deploy Gates

All must be green before opening the PR:

- [ ] **Build clean:** `bun run build` in `frontend/` exits 0, zero TS errors ← already verified 2026-05-09
- [ ] **Backend commits staged:** `app/api/routes/auth.py` + `app/config.py` committed in a separate commit (`fix(auth): backend clerk migration`) before the GH-10 commit
- [ ] **No secrets in diff:** `git diff origin/main...HEAD` contains no `sk_live_`, `sk_test_`, or `pk_live_`
- [ ] **Clerk dashboard configured:** Application exists, GitHub + Google social providers enabled, allowed redirect URLs include Railway preview URL + `https://your-prod-domain`
- [ ] **Railway env vars set:** `VITE_CLERK_PUBLISHABLE_KEY` and `CLERK_SECRET_KEY` set in Railway service environment before deploy
- [ ] **`.env.example` in diff:** Confirms Clerk key stubs are documented

---

## Deployment Steps

### Phase 1 — Commit

```bash
# Step 1: Commit pre-existing backend migration separately
git add app/api/routes/auth.py app/config.py
git commit -m "fix(auth): backend Clerk JWKS migration (RS256 verify, require_auth)"

# Step 2: Commit GH-10 frontend + env changes
git add frontend/package.json frontend/bun.lock \
        frontend/src/main.tsx \
        frontend/src/api/client.ts \
        frontend/src/components/ProtectedRoute.tsx \
        frontend/src/pages/LoginPage.tsx \
        .env.example \
        .claude/task-progress/GH-10.md \
        docs/GH-10/
git commit -m "feat(auth): Clerk zero-credential social login (GH-10)

- Install @clerk/clerk-react@5.61.3
- Wrap app in ClerkProvider + ClerkTokenSync in main.tsx
- Replace localStorage auth with Clerk JWT in client.ts (initClerkAuth)
- ProtectedRoute now uses useAuth().isSignedIn guard
- LoginPage replaced with Clerk <SignIn /> hosted UI
- Document VITE_CLERK_PUBLISHABLE_KEY + CLERK_SECRET_KEY in .env.example

Closes #10"

# Step 3: Push branch
git push -u origin feature/GH-10-clerk-zero-credential-auth

# Step 4: Sync beads
bd dolt push
```

### Phase 2 — PR + Preview Deploy

```bash
gh pr create \
  --title "feat(auth): Clerk zero-credential social login" \
  --body "Closes #10. Replaces shared-password HS256 auth with Clerk social login (GitHub/Google/magic link). ClerkProvider + ClerkTokenSync pattern wires Clerk's async getToken into the plain-module fetchAPI without violating hook rules. Backend JWKS verification pre-landed."
```

- Railway will auto-deploy a preview environment on PR open.
- Copy the Railway preview URL → add it to Clerk dashboard → Allowed redirect URLs.

### Phase 3 — Validation (Preview)

Run through the test plan from the spec:

- [ ] Navigate to preview URL → redirected to `/login`, Clerk `<SignIn />` visible
- [ ] Complete GitHub OAuth flow → redirected back to `/`, app loads
- [ ] Complete Google OAuth flow → same
- [ ] Open DevTools Network → all API requests carry `Authorization: Bearer <jwt>` with `alg: RS256`
- [ ] Call `GET /api/v1/auth/verify` with token → `{"valid": true, "user_id": "user_..."}`
- [ ] Create a session, send a chat message, view ledger → all succeed (regression check)
- [ ] Attempt `POST /api/v1/auth/login` → 404

### Phase 4 — Production

Once preview validation passes:

```bash
# Merge PR (Railway deploys to production on merge to main)
gh pr merge --squash

# Verify production
# Same validation checklist as Phase 3 against prod URL
```

---

## Rollback Plan

| Scenario | Rollback Action |
|----------|-----------------|
| Frontend broken after merge | `git revert HEAD` on main → Railway auto-redeploys prior build |
| VITE_CLERK_PUBLISHABLE_KEY wrong/missing | Update in Railway dashboard → redeploy (no code change) |
| CLERK_SECRET_KEY wrong → all auth 500 | Update in Railway dashboard → redeploy |
| Clerk dashboard misconfigured (wrong redirect URL) | Add correct URL in Clerk dashboard → instant (no redeploy needed) |
| Catastrophic: need to restore old password auth | Not recommended — old auth endpoint removed. Restore from git history: `git show origin/main:app/api/routes/auth.py` + revert frontend changes. Estimated: 30 min. |

> Note: There is no "revert to shared password" fast path once this merges. The old `/auth/login` endpoint is gone. Ensure Clerk is confirmed working on the preview before merging to main.

---

## Risk Flags

| Risk | Severity | Mitigation |
|------|----------|------------|
| Clerk redirect URL not whitelisted for Railway preview | HIGH | Add preview URL to Clerk dashboard before testing |
| `VITE_CLERK_PUBLISHABLE_KEY` missing from Railway → white screen | HIGH | Verify Railway env vars before deploy; startup assertion in `main.tsx` throws readable error |
| Social provider not enabled in Clerk dashboard | MEDIUM | Enable GitHub + Google in Clerk dashboard → Social Connections |
| JWKS thundering herd (ACID WARN from review) | LOW | Single Railway instance — not a concern at current scale |
| `ClerkTokenSync` registers after first API call | LOW | `ClerkTokenSync` renders before `QueryClientProvider` in the tree; Clerk hydrates before any route mounts |

---

## Sign-Off

- [ ] Drew Schillinger — pre-deploy gates verified
- [ ] Drew Schillinger — preview validation complete
- [ ] Drew Schillinger — approved to merge
