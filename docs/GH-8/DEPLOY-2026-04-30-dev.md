## Deployment Manifest — GH-8 (dev)

**Task:** GH-8 — Truth-O-Meter UI
**Date:** 2026-04-30
**Environment:** `dev` (local)
**Branch:** `feature/gh-8-truth-o-meter`
**Commit (working tree pre-commit):** `7d52b82`
**Platform:** Local — `docker compose` + `bun run dev` + `uvicorn`

---

### Pre-Deploy Gates

- [x] QA: **PASS WITH NOTES** — `docs/GH-8/QA.md`
- [x] REVIEW.md BLOCKs: **0 unresolved** — `docs/GH-8/REVIEW.md` (APPROVE)
- [x] Drift: **ALIGNED 13/13** — `docs/GH-8/DRIFT.md`
- [ ] Migrations applied to local DB (manual step below)
- [x] Env vars provisioned (existing `.env`)
- [x] Team confirmed (solo — Drew Schillinger)

---

### What Changed

Backend (5 files): new `_compute_truth_score` in `app/agents/arbiter.py`; `truth_score` field added to `ArbiterAnalysis`, `ChatResponse`, `MessageResponse`, `Message` ORM, and the persistence + return paths in `app/services/chat.py` + `app/api/routes/chat.py`.

Migration (1 new file): `migrations/002_add_message_truth_score.sql` — idempotent `ALTER TABLE messages ADD COLUMN IF NOT EXISTS truth_score INTEGER NULL`.

Frontend (3 files): new `TruthOMeter.tsx` (210 LOC, hand-rolled SVG with R&M zone scale and `DEFAULT_ZONES` export); `Message` and `ChatResponse` interfaces extended with `truth_score`; `SessionPage.tsx` imports and mounts the gauge above the chat scroll container, fed from the latest `agent`-role message's score.

### Migrations

| File | Action | Rollback |
|---|---|---|
| `migrations/002_add_message_truth_score.sql` | Apply via `psql … -f` | `ALTER TABLE messages DROP COLUMN truth_score;` |

R1 (committed): pending the commit step below.
R2 (rollback script): N/A — project convention has none; one-line drop documented above.
R3 (cross-team): N/A — solo project.

### Config Changes

(none)

---

### Deployment Steps (dev)

#### Step 1 — Commit the implementation changes
```bash
git add \
  app/agents/arbiter.py \
  app/api/routes/chat.py \
  app/db/models.py \
  app/schemas/chat.py \
  app/services/chat.py \
  migrations/002_add_message_truth_score.sql \
  frontend/src/components/TruthOMeter.tsx \
  frontend/src/pages/SessionPage.tsx \
  frontend/src/types/index.ts \
  docs/GH-8/

git commit -m "feat(GH-8): Truth-O-Meter — animated SVG gauge for arbiter confidence

Adds a deterministic 0-100 truth score to ArbiterAnalysis (computed
from contradiction/unsupported flag count + per-fact confidence),
persists it on the agent-role Message row via a new nullable column
(migration 002), and renders an animated semicircular SVG gauge in
SessionPage with R&M-themed zone labels.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

#### Step 2 — Bring up the local Postgres
```bash
docker compose -f docker/docker-compose.yml up -d
# Wait for healthy (5-10s):
docker compose -f docker/docker-compose.yml ps
```

#### Step 3 — Apply migration 002
```bash
psql -h localhost -U depo -d deposition_prep \
  -f migrations/002_add_message_truth_score.sql
# Expect: ALTER TABLE
# Verify:
psql -h localhost -U depo -d deposition_prep \
  -c "\d messages" | grep truth_score
# Expect: truth_score | integer | nullable
```

#### Step 4 — Backend smoke
```bash
# In one terminal:
uvicorn app.main:app --reload --port 8000
# Sanity check:
curl -s http://localhost:8000/health
```

#### Step 5 — Frontend dev server
```bash
# In another terminal:
cd frontend
bun install
bun run dev
# Should open at http://localhost:5173 (vite default)
```

#### Step 6 — Visual smoke (covers REVIEW NIT-1)
1. Open http://localhost:5173 in Chrome (or whatever the presenter laptop will use)
2. Log in / start a session against an existing or new witness profile
3. Send a witness response that the arbiter will analyze
4. **Verify:** `<TruthOMeter />` renders above the chat panel
5. **Verify:** needle starts at neutral idle, then visibly swings to the computed score over ~1.2s
6. **Verify:** zone label updates (e.g. "Aw Jeez, Maybe?" for ~50, "C-137 Canon Event" for ~85+)
7. **Verify:** existing `arbiter_flags` badges still render below the message (AC #12 backwards-compat)
8. **Verify:** refresh the page — gauge restores to last persisted score (AC #5)
9. Open DevTools → Inspect the gauge → confirm `transform: rotate(...)` + `transition` are applied
10. Test `transformBox: 'view-box'` compat: confirm rotation is around the gauge center, not viewport top-left

#### Step 7 — Optional: file follow-up tickets surfaced during deploy
- **Test infrastructure** — separate ticket; QA.md flagged the project-wide gap.
- **Penalty-weight tuning** — separate ticket; spec flagged as open question, ACs pin current weights.
- **CI workflow uses `OPENAI_API_KEY`** — pre-existing GH-2 leftover; should reference `ANTHROPIC_API_KEY`.

---

### Validation Steps

| # | Check | How |
|---|---|---|
| 1 | Truth-O-Meter renders | Step 6.4 |
| 2 | Score derivation matches AC #1, #2, #3 | Already verified via algorithm test during /implement |
| 3 | Animation observable on stage | Step 6.5 |
| 4 | Backwards-compat with FlagBadge | Step 6.7 |
| 5 | Persistence across refresh | Step 6.8 |
| 6 | No JS console errors during interaction | Step 6.9 DevTools |

---

### Rollback Plan

**Code:** `git revert HEAD` (after Step 1 commit) or `git checkout main` if not yet committed.
**DB:** `psql -h localhost -U depo -d deposition_prep -c "ALTER TABLE messages DROP COLUMN truth_score;"` — column is nullable and isolated.
**Servers:** restart `uvicorn` and `bun run dev` after checkout.

---

### Team Roster

| Role | Person |
|---|---|
| Executor | Drew Schillinger |
| Verifier | Drew Schillinger |
| Rollback authority | Drew Schillinger |

---

### Risk Flags

| Source | Item | Status |
|---|---|---|
| QA (PASS WITH NOTES) | Penalty weights best-guess | Tunable post-demo, ACs lock current values |
| QA (PASS WITH NOTES) | No project-wide test infra | Pre-existing; follow-up ticket recommended |
| REVIEW NIT-1 | `transformBox` browser compat | Step 6.10 smoke covers this |
| REVIEW NIT-2 | Custom zones non-exhaustive | DEFAULT_ZONES is exhaustive; only bites if GH-9/GH-6 override sparsely |
| Pre-existing | CI workflow still references `OPENAI_API_KEY` | GH-2 follow-up — does not block dev |
| Strategic | GH-7 DB will be ghost.build (decision today) | Captured in `bd memories` + GitHub issue #7 |

---

*All gates above must be checked before executing.*
*Manifest generated by /drew-deploy.*
