## Preflight Checklist — GH-8

**Task:** GH-8 — Truth-O-Meter UI
**Date:** 2026-04-30
**Branch:** `feature/gh-8-truth-o-meter`
**Commit (working tree, not yet committed):** `7d52b82` (branch base; implementation diff still uncommitted)
**Environment:** `dev` (local)
**Platform:** Local — `docker compose` (Postgres + pgvector) + `bun run dev` (frontend) + `uvicorn` (backend)
**Spec:** `docs/GH-8/SPEC.md`

> **Strategic decision (logged this session):** GH-7's hosted DB will be **ghost.build** (not Neon/Supabase). Captured in `bd memories gh-7-db-choice-ghost-build-chosen-2026` + GitHub issue #7 comment. Out of scope for this deploy.

---

### Changed Files

**New (2):**
- `frontend/src/components/TruthOMeter.tsx` (210 LOC) — hand-rolled SVG gauge
- `migrations/002_add_message_truth_score.sql` (17 LOC) — `ALTER TABLE messages ADD COLUMN IF NOT EXISTS truth_score INTEGER NULL;`

**Modified (8):**
- `app/agents/arbiter.py` — `truth_score` on `ArbiterAnalysis`; new `_compute_truth_score`; Step 7 in `analyze_response`
- `app/schemas/chat.py` — `truth_score` on `ChatResponse` + `MessageResponse`
- `app/db/models.py` — `truth_score` column on `Message` (Mapped[int|None])
- `app/services/chat.py` — persist + return `truth_score`
- `app/api/routes/chat.py` — map `truth_score` in `MessageResponse` build
- `frontend/src/types/index.ts` — `truth_score` on `Message` + `ChatResponse`
- `frontend/src/pages/SessionPage.tsx` — mount `<TruthOMeter />`, derive `latestAgentScore`
- `frontend/tsconfig.tsbuildinfo` — auto-regenerated build artifact

**Deleted:** none

### New Dependencies

(none — `frontend/package.json` unchanged, no Python deps added)

### Environment Variables

(none detected in diff — no `process.env`, `import.meta.env`, or `os.getenv` references added)

For local `dev` to work, the existing `.env` must already provide:
- `DATABASE_URL` (`postgresql+asyncpg://depo:localdev@localhost:5432/deposition_prep`)
- `ANTHROPIC_API_KEY` (post-GH-2 — the CI workflow at `.github/workflows/deploy.yml:42` still references `OPENAI_API_KEY`, leftover from pre-GH-2)

### Migrations / Schema Changes

| File | Type | Idempotent | Rollback |
|---|---|---|---|
| `migrations/002_add_message_truth_score.sql` | `ALTER TABLE … ADD COLUMN IF NOT EXISTS` | Yes | None (matches `001_add_witness_profiles.sql` convention — project has no rollback-script pattern) |

For dev: `psql -h localhost -U depo -d deposition_prep -f migrations/002_add_message_truth_score.sql` after `docker compose up -d`.

### Risk Flags

**From REVIEW.md:** 0 BLOCKs, 5 non-blocking NITs (transformBox browser-compat smoke test on presenter laptop; `findZone` non-exhaustive zones; `colorClass`/`currentColor` rationale comment; two-pass message filter; FlagBadge raw Tailwind colors vs gauge tokens — defer to GH-9).

**From DRIFT.md:** 0 SPEC_GAP, 0 IMPL_GAP, 0 unintentional SCOPE_DRIFT — ALIGNED 13/13.

**From QA.md (PASS WITH NOTES):**
- Penalty weights are best-guess; tune post-first-demo
- Test infrastructure missing project-wide — separate ticket recommended
- Migration manual application required (no Alembic, no auto-migrate in deploy workflow)
- Visual smoke not yet performed in a live browser

**From engineer-supplied gotchas:** none beyond above. CI workflow still references `OPENAI_API_KEY` — pre-existing concern, GH-2 follow-up.

---

### Pre-Deploy Gate Checklist

- [x] QA verdict: **PASS WITH NOTES** — `docs/GH-8/QA.md`
- [x] REVIEW.md BLOCKs: **0 unresolved** — `docs/GH-8/REVIEW.md` (APPROVE)
- [x] Drift verdict: **ALIGNED 13/13** — `docs/GH-8/DRIFT.md`
- [ ] Working-tree changes committed to `feature/gh-8-truth-o-meter`
- [x] Migrations committed to source control (R1) — pending the commit step
- [N/A] Migration rollback scripts (R2) — project convention has none; matches `001_…`
- [x] Env vars provisioned for dev (existing `.env`)
- [x] Team roster confirmed — solo (Drew Schillinger as executor + verifier + rollback authority)
- [x] Timing/dependency constraints satisfied — none for dev target
- [N/A] PR reviewed and approved — dev target, not merging to main

---

### Rollback Plan (dev)

1. **Code rollback:** `git checkout main` (working tree changes are uncommitted; reverting is just switching branches). If committed: `git checkout main` on the branch.
2. **DB rollback:** `psql -h localhost -U depo -d deposition_prep -c "ALTER TABLE messages DROP COLUMN truth_score;"` — column is nullable and isolated, drop is safe.
3. **Frontend dev server:** `bun run dev` will hot-reload to whatever branch is checked out.
4. **Backend dev server:** restart `uvicorn` after checkout.

For prod (when GH-7 lands and we deploy via Railway / Vercel + ghost.build): TBD in that ticket's manifest.
