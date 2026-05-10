# SPEC: GH-10 — feat(auth): Clerk zero-credential social login

**Ticket:** GH-10 / Councel_of_Ricks-ap5
**Date:** 2026-05-09
**Author:** Drew Schillinger (via Spec Writer Agent)
**Status:** Draft

---

## Problem

The app currently uses a single bcrypt-hashed password stored as an env var (`CLERK_SECRET_KEY` predecessor fields) with custom HS256 JWTs that carry no `sub` claim. This means every user shares one credential, there is no user identity, and no per-user data isolation is possible. The backend was partially migrated to Clerk JWKS verification in a prior session, leaving the frontend in a broken intermediate state: `api/client.ts:71` still calls `POST /auth/login` with a password — an endpoint that no longer exists. This ticket completes the migration end-to-end, making the app publicly accessible with proper multi-user Clerk auth via social login (GitHub, Google) or magic link.

---

## Technical Constraints

- **React 18.3.1** (`frontend/package.json:16`) — hooks-based patterns only; no class components
- **Vite 6 + TypeScript 5.7** — env vars exposed to browser must be prefixed `VITE_`; server env vars must not carry the `VITE_` prefix
- **react-router-dom 7.1** (`frontend/package.json:17`) — `<Route>` / `useNavigate` patterns already in place; do not restructure routing
- **FastAPI + python-jose** — backend already uses `jose.jwt` for RS256 decode; no new Python JWT library needed
- **`@clerk/clerk-react` not yet installed** — must be added to `frontend/package.json` as a production dependency; version to install is whatever is current stable at implementation time
- **`auth_disabled=True` must continue to work** — local dev without a Clerk account must remain functional; `require_auth` already returns `"dev-user"` in this mode and must not be changed
- **Backend is already migrated** — `app/api/routes/auth.py` and `app/config.py` are complete; no backend Python changes are required by this spec unless a defect is discovered
- **No passwords or tokens stored server-side** — Clerk is the identity provider; the backend only verifies JWTs, it never issues them
- **`exportQuestions` in `client.ts:249-268`** calls `getToken()` directly (not through `fetchAPI`) — this call site must also be updated to use the Clerk async token getter

---

## Solution

### Approach

Install `@clerk/clerk-react`, wrap the app in `ClerkProvider` in `main.tsx`, and wire Clerk's async `getToken` into the existing `fetchAPI` function via a module-level initializer (`initClerkAuth`). Replace `ProtectedRoute` with a Clerk-aware gate using `useAuth().isSignedIn`. Replace `LoginPage` with a Clerk `<SignIn />` render. Delete all localStorage token helpers and the dead `login()` function from `client.ts`. Document the two new env vars in `.env.example`.

The approach deliberately keeps `App.tsx` and all route definitions unchanged — only the internals of `ProtectedRoute`, `LoginPage`, `client.ts`, and `main.tsx` change.

### Design

#### Token flow (end-to-end)

```
User hits protected route
  → ProtectedRoute checks useAuth().isSignedIn
  → if false: redirect to /login (Clerk <SignIn /> hosted UI)
  → if true: render children

Child page calls fetchAPI(...)
  → fetchAPI calls await _clerkGetToken()
  → _clerkGetToken was set by initClerkAuth(getToken) inside ClerkTokenSync
  → returns short-lived RS256 JWT issued by Clerk
  → sent as Authorization: Bearer <token>
  → FastAPI require_auth() verifies via JWKS, returns sub as user_id
```

#### `ClerkTokenSync` component

A small React component rendered as an immediate child of `ClerkProvider` (and therefore able to call `useAuth()`). Its only job: on mount, call `initClerkAuth(getToken)` from `useAuth()` to register the async getter in `client.ts`. It renders nothing (`return null`).

This is necessary because `useAuth()` is a hook — it cannot be called outside a React component tree, and `client.ts` is a plain module. The initializer pattern threads the hook's `getToken` into the module without violating hook rules.

#### `client.ts` token module rewrite

Remove:
- `TOKEN_KEY` constant (`line 16`)
- `getToken()` (`line 19`)
- `setToken()` (`line 23`)
- `clearToken()` (`line 27`)
- `isAuthenticated()` (`line 31`)
- `login()` function (`lines 71-82`)
- `logout()` function (`lines 84-87`) — replaced by Clerk's `signOut`

Add:
- `let _clerkGetToken: (() => Promise<string | null>) | null = null`
- `export function initClerkAuth(fn: () => Promise<string | null>): void` — stores the getter

Modify:
- `fetchAPI` — replace `const token = getToken()` with `const token = requireAuth ? await _clerkGetToken?.() ?? null : null`
- `fetchAPI` 401 handler — remove `clearToken()`; redirect to `/login` is sufficient
- `exportQuestions` (`lines 249-268`) — replace inline `getToken()` call with `await _clerkGetToken?.()`

#### `ProtectedRoute.tsx` rewrite

```tsx
import { useAuth } from '@clerk/clerk-react'
import { Navigate } from 'react-router-dom'

export default function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { isSignedIn, isLoaded } = useAuth()
  if (!isLoaded) return null          // Clerk hydrating — render nothing
  if (!isSignedIn) return <Navigate to="/login" replace />
  return <>{children}</>
}
```

#### `LoginPage.tsx` rewrite

Replace the entire password form with Clerk's hosted `<SignIn />` component. Remove import of `login` from `api/client`.

```tsx
import { SignIn } from '@clerk/clerk-react'

export default function LoginPage() {
  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-100">
      <SignIn />
    </div>
  )
}
```

#### `main.tsx` changes

Wrap the existing provider tree with `ClerkProvider` and add `ClerkTokenSync` inside it, before `QueryClientProvider`.

```tsx
import { ClerkProvider } from '@clerk/clerk-react'
// ... existing imports

function ClerkTokenSync() {
  const { getToken } = useAuth()
  // Effect runs once on mount — registers getter in client.ts module
  React.useEffect(() => { initClerkAuth(getToken) }, [getToken])
  return null
}

ReactDOM.createRoot(...).render(
  <React.StrictMode>
    <ClerkProvider publishableKey={import.meta.env.VITE_CLERK_PUBLISHABLE_KEY}>
      <ClerkTokenSync />
      <QueryClientProvider client={queryClient}>
        <BrowserRouter>
          <App />
        </BrowserRouter>
      </QueryClientProvider>
    </ClerkProvider>
  </React.StrictMode>
)
```

Note: `ClerkTokenSync` calls `useAuth()`, which requires being rendered inside `ClerkProvider`. It must be placed as a direct child of `ClerkProvider`, before `QueryClientProvider`, so it runs before any protected routes attempt API calls.

#### God Object Gate

The design routes auth concerns through four files, each with a single responsibility:
- `client.ts` — HTTP transport + token injection (one concern)
- `ProtectedRoute.tsx` — route guard (one concern)
- `LoginPage.tsx` — sign-in UI (one concern)
- `main.tsx` — provider tree assembly (one concern)

No single file owns state for 3+ unrelated domains. No god object is introduced. Gate passed.

### Files to Change

| File | Change | Why |
|------|--------|-----|
| `frontend/package.json` | Add `@clerk/clerk-react` to `dependencies` | SDK not present; all Clerk hooks and components require it |
| `frontend/src/main.tsx` | Wrap app in `ClerkProvider`; add `ClerkTokenSync` component; import `initClerkAuth` from `client.ts` | Entry point for Clerk context; `ClerkTokenSync` registers the async token getter |
| `frontend/src/api/client.ts` | Remove `TOKEN_KEY`, `getToken`, `setToken`, `clearToken`, `isAuthenticated`, `login`, `logout`; add `initClerkAuth`; make `fetchAPI` async token-aware; update `exportQuestions` inline token call | Eliminates dead localStorage auth; connects token flow to Clerk |
| `frontend/src/components/ProtectedRoute.tsx` | Replace passthrough with `useAuth().isSignedIn` guard | Currently renders children unconditionally — no auth enforcement |
| `frontend/src/pages/LoginPage.tsx` | Replace password form with `<SignIn />` from `@clerk/clerk-react`; remove `login` import | Password form calls dead endpoint; Clerk provides hosted UI |
| `.env.example` | Add `VITE_CLERK_PUBLISHABLE_KEY` and `CLERK_SECRET_KEY` entries with comments | Neither key is documented; developers cloning the repo have no guidance |

### What This Does NOT Change

- `App.tsx` — route definitions are unchanged; `ProtectedRoute` wrapper pattern is preserved
- `app/api/routes/auth.py` — backend is already migrated; no changes required
- `app/config.py` — `clerk_secret_key` and `auth_disabled` already present
- Any other `frontend/src/api/client.ts` functions (sessions, chat, profiles, questions, clerk agent) — only the auth layer changes, not the API call shapes
- Database schema, models, or migrations — no user table changes are part of this ticket
- The `auth_disabled=True` local dev path — must continue to work unchanged

---

## Acceptance Criteria

1. GIVEN a user is not signed in WHEN they navigate to any protected route (`/`, `/profiles`, `/clerk`, `/session/:id`) THEN they are redirected to `/login` and see the Clerk `<SignIn />` component
2. GIVEN a user completes GitHub, Google, or magic link login via Clerk WHEN the sign-in flow completes THEN they are redirected to the originally requested protected route and the app is fully functional
3. GIVEN a signed-in user's session is active WHEN `fetchAPI` makes any authenticated request THEN the `Authorization: Bearer` header carries a Clerk-issued RS256 JWT (not a localStorage value)
4. GIVEN a valid Clerk JWT WHEN `GET /auth/verify` is called THEN the backend returns `{"valid": true, "user_id": "<clerk_sub>"}` where `user_id` is the Clerk `sub` claim
5. GIVEN `auth_disabled=True` in config WHEN the backend processes any authenticated request THEN `require_auth` returns `"dev-user"` without contacting Clerk (local dev unaffected)
6. GIVEN the current codebase WHEN a developer searches for `getToken`, `setToken`, `clearToken`, `TOKEN_KEY`, `isAuthenticated`, `login(password`, `logout()` in `frontend/src/api/client.ts` THEN none of these symbols exist
7. GIVEN the current codebase WHEN a developer calls `POST /auth/login` THEN the server returns 404 (endpoint removed, confirmed absent from `auth.py`)
8. GIVEN a fresh repo clone WHEN a developer reads `.env.example` THEN they see documented entries for both `VITE_CLERK_PUBLISHABLE_KEY` and `CLERK_SECRET_KEY` with explanatory comments
9. GIVEN `@clerk/clerk-react` is installed WHEN `npm run build` is run in `frontend/` THEN TypeScript compilation succeeds with zero errors

---

## Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| `ClerkTokenSync` renders before `ClerkProvider` hydrates, causing `initClerkAuth` to be called with a stale `getToken` | Low | Medium | `useEffect` with `[getToken]` dep means it re-registers if `getToken` identity changes; Clerk guarantees stable reference after hydration |
| `exportQuestions` raw `fetch` call is missed during client.ts cleanup | Medium | Medium | Explicitly listed in Files to Change; acceptance criterion 6 covers symbol search verification |
| Clerk `publishableKey` missing at runtime causes white screen | Medium | High | Criterion 8 covers `.env.example` documentation; add a startup assertion in `ClerkProvider` — if `VITE_CLERK_PUBLISHABLE_KEY` is empty, render a visible error rather than crashing silently |
| `react-router-dom` v7 `<Navigate>` API change from v6 | Low | Low | `<Navigate to="..." replace />` pattern is unchanged between v6 and v7; verify at implementation time |
| Clerk JWKS cache (`_jwks_cache`) is module-level and never invalidated beyond key rotation | Low | Low | Current implementation already handles rotation via cache invalidation on unknown `kid`; no change needed |

---

## Dependencies

- [ ] External: Clerk account required — create application at dashboard.clerk.com, enable GitHub + Google social providers, obtain `CLERK_SECRET_KEY` (backend) and `VITE_CLERK_PUBLISHABLE_KEY` (frontend)
- [ ] Internal: Backend migration (auth.py + config.py) — already complete as of this session; this ticket assumes that state

---

## Test Plan

**Manual verification (primary path — no test suite currently exists):**
1. Set `VITE_CLERK_PUBLISHABLE_KEY` and `CLERK_SECRET_KEY` from a Clerk test environment
2. `npm run dev` in `frontend/` — confirm no TypeScript errors
3. Navigate to `http://localhost:5173/` — confirm redirect to `/login`
4. Complete GitHub OAuth flow — confirm redirect back to `/`
5. Open browser DevTools Network tab — confirm all API requests carry `Authorization: Bearer <jwt>` where the JWT header `alg` is `RS256`
6. Call `GET /api/v1/auth/verify` with the token — confirm `{"valid": true, "user_id": "user_..."}` response
7. Set `auth_disabled=True` in backend `.env` — confirm app loads without Clerk keys present
8. Search `client.ts` for removed symbols (see AC 6) — confirm all absent
9. Attempt `POST /api/v1/auth/login` — confirm 404

**Build gate:**
- `npm run build` in `frontend/` must exit 0 with zero TypeScript errors

**Regression check:**
- After login, create a session, send a chat message, view the ledger — confirm all API calls succeed (auth header forwarding unbroken by `fetchAPI` rewrite)

---

## Model Router

Files to Change count: **6 files across 2 top-level modules** (`frontend/` and repo root `.env.example`). The change touches a shared contract (the `initClerkAuth` interface between `main.tsx` and `client.ts`) and introduces a new provider architecture pattern.

**Decision: Opus / Enterprise Architect** — 6 files, 2 modules, shared contract change (token injection interface), architecture decision (ClerkTokenSync pattern).

---

## Sources

- `app/config.py:64-66` (branch: main, commit: 2607017) — confirms `clerk_secret_key: str = ""` and `auth_disabled: bool = False` are present in Settings
- `app/api/routes/auth.py:1-99` (branch: main, commit: 0f52a4c) — confirms backend is fully migrated: `_CLERK_JWKS_URL`, `_jwks_cache`, `_fetch_jwks`, `_verify_clerk_token`, `require_auth` returning `str` user_id, `GET /auth/verify` endpoint; no `/auth/login` endpoint present
- `app/api/routes/auth.py:17-18` (branch: main, commit: 0f52a4c) — confirms `_CLERK_JWKS_URL = "https://api.clerk.com/v1/jwks"` and `_jwks_cache: dict[str, dict] = {}`
- `app/api/routes/auth.py:79-99` (branch: main, commit: 0f52a4c) — confirms `require_auth` signature: `async def require_auth(...) -> str`, returns `"dev-user"` when `auth_disabled`, raises 401/500 otherwise
- `frontend/src/api/client.ts:16` (branch: main, commit: 0f52a4c) — confirms `TOKEN_KEY = 'dps_auth_token'` exists and must be removed
- `frontend/src/api/client.ts:19-33` (branch: main, commit: 0f52a4c) — confirms `getToken`, `setToken`, `clearToken`, `isAuthenticated` all present using localStorage; all must be removed
- `frontend/src/api/client.ts:35-68` (branch: main, commit: 0f52a4c) — confirms `fetchAPI` structure: reads token via `getToken()` at line 46, clears token on 401 at line 57; both call sites must be updated
- `frontend/src/api/client.ts:71-82` (branch: main, commit: 0f52a4c) — confirms dead `login()` function calling `POST /auth/login` with password; must be removed
- `frontend/src/api/client.ts:84-87` (branch: main, commit: 0f52a4c) — confirms `logout()` calls `clearToken()` and redirects; must be removed (replaced by Clerk `signOut`)
- `frontend/src/api/client.ts:249-268` (branch: main, commit: 0f52a4c) — confirms `exportQuestions` contains an out-of-band raw `fetch` call with inline `getToken()` at line 250; this call site must also be updated
- `frontend/src/components/ProtectedRoute.tsx:5-7` (branch: main, commit: 3c788c2) — confirms current implementation is a passthrough (`return <>{children}</>`) with no auth logic
- `frontend/src/pages/LoginPage.tsx:1-75` (branch: main, commit: 0f52a4c) — confirms password form with `login(password)` call from `api/client`; entire component must be replaced
- `frontend/src/main.tsx:1-26` (branch: main, commit: 0806238) — confirms current provider tree: `StrictMode > QueryClientProvider > BrowserRouter > App`; `ClerkProvider` must wrap the outside
- `frontend/src/App.tsx:1-51` (branch: main, commit: 3c788c2) — confirms five routes using `ProtectedRoute` wrapper: `/`, `/profiles`, `/clerk`, `/session/:sessionId`; `App.tsx` itself does not change
- `frontend/package.json:12-18` (branch: main, commit: 0f52a4c) — confirms `@clerk/clerk-react` is absent from dependencies; must be added
- `.env.example:1-21` (branch: main, commit: 606c0fb) — confirms neither `VITE_CLERK_PUBLISHABLE_KEY` nor `CLERK_SECRET_KEY` are documented; both must be added
