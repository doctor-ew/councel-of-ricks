## Code Review (drew-review)

**Task:** GH-10
**Date:** 2026-05-09
**Mode:** post-impl (working tree vs origin/main)
**Scope:** 6 files (frontend: main.tsx, client.ts, ProtectedRoute.tsx, LoginPage.tsx, package.json; backend: auth.py, config.py)
**Reviewer:** drew-review harness

---

### DRY
| Severity | Confidence | Finding | Location |
|----------|-----------|---------|----------|
| NOTE | LOW | `exportQuestions` duplicates Bearer token injection already in `fetchAPI` (manual fetch + manual `Authorization` header). Spec-documented intentional second call site — returns `response.text()` not `response.json()`, so `fetchAPI` can't wrap it without a refactor. | `frontend/src/api/client.ts:219-231` |

### SOLID
| Severity | Confidence | Principle | Finding | Location |
|----------|-----------|-----------|---------|----------|
| WARN | MEDIUM | S — Single Responsibility | `_verify_clerk_token` resets `_jwks_cache = {}` (lines 50-51) to force a refresh on unknown kid. Cache lifecycle belongs in `_get_jwks`, not the verification function. If a third call site ever does key lookup, cache management leaks further. | `app/api/routes/auth.py:49-52` |
| NOTE | LOW | D — Dependency Inversion | `settings = get_settings()` at module level (line 15) wires a concrete dependency into module scope. Established project pattern and `lru_cache` makes it effectively DI, so no action required. | `app/api/routes/auth.py:15` |

### ACID
| Severity | Confidence | Property | Finding | Location |
|----------|-----------|----------|---------|----------|
| WARN | MEDIUM | I — Isolation | `_jwks_cache` is an unprotected module-level dict mutated across `await` boundaries. On a cold start or forced invalidation, concurrent requests all see the empty cache simultaneously and each fires `_fetch_jwks()`. Writes are idempotent (same data) so result is correct, but under thundering-herd load this could hammer Clerk's JWKS endpoint. No `asyncio.Lock` guards the fetch. | `app/api/routes/auth.py:32-52` |

### CoC
| Severity | Confidence | Finding | Location |
|----------|-----------|---------|----------|
| NOTE | LOW | `ClerkTokenSync` is defined inline in `main.tsx` rather than in `src/components/`. Repo convention is one component per file under `components/`. Acceptable here — it's a zero-render side-effect shim with no props interface, and moving it would create a circular import between `components/ClerkTokenSync.tsx` and `api/client.ts`. | `frontend/src/main.tsx:26-32` |

### Big O
| Severity | Confidence | Complexity | Finding | Location |
|----------|-----------|-----------|---------|----------|
| — | — | — | No findings. JWKS dict is O(n) over key count (typically 2), kid lookup is O(1). | — |

### LLM Trust Boundary
| Severity | Confidence | Vector | Finding | Location |
|----------|-----------|--------|---------|----------|
| NOTE | LOW | Error verbosity | `detail=f"Token verification failed: {exc}"` passes the raw `JWTError` string to the API response body. `python-jose` error messages ("Signature verification failed", "Token is expired") are not exploitable but reveal implementation details to unauthenticated callers. Consider a fixed `"Token invalid"` string in prod. | `app/api/routes/auth.py:65` |

---

### Summary
- BLOCK: 0
- WARN:  2 (SOLID/SRP in auth.py, ACID/I in auth.py)
- NOTE:  4

### Trend (vs last run)
First review for GH-10 — no deltas to compare.

### Verdict
**APPROVE**

Zero blocking findings. Two MEDIUM WARNs in `auth.py` — both in the JWKS cache layer:
1. Cache invalidation logic bleeds into `_verify_clerk_token` (SRP). Recommended fix: extract a `_invalidate_jwks_cache()` helper called from `_verify_clerk_token`.
2. No `asyncio.Lock` on cache refresh — thundering herd risk at cold start. Low priority for current single-instance deployment; worth addressing before horizontal scale.

Neither blocks shipping.
