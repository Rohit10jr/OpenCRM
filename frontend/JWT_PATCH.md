# The frappe-ui JWT patch

**Read this before upgrading `frappe-ui`.** An upgrade that resets `main.js` will
silently revert the patch and every request will go out unauthenticated.

## Why

`PORT_PLAN.md` section 10 and `specs/PHASE_0_FOUNDATION.md` section 7: the Django port
authenticates with JWT bearer tokens, not Frappe's `sid` session cookie. This is the
**only** sanctioned deviation from the Frappe wire protocol - the 225 `createResource` /
`createListResource` / `createDocumentResource` call sites are untouched, and every URL,
parameter name and response envelope is unchanged.

## What changed - four files, ~20 lines

| File | Change |
|---|---|
| `src/auth/tokens.js` | **New.** Token storage + `user_id` claim decode |
| `src/auth/jwtRequest.js` | **New.** Wraps `frappeRequest`: attaches the header, refreshes once on 401 |
| `src/main.js` | `setConfig('resourceFetcher', frappeRequest)` -> `jwtRequest`; same for the dev boot call |
| `src/stores/session.js` | `sessionUser()` reads the token instead of the `user_id` cookie; `login` stores the pair; `logout` clears it |

The integration point is one line, because frappe-ui centralises HTTP:

```js
setConfig('resourceFetcher', jwtRequest)   // was: frappeRequest
```

## Backend contract

| Endpoint | Returns |
|---|---|
| `POST /api/method/login` (`usr`, `pwd`) | `{"message": {"access", "refresh", "user", "full_name", ...}}` |
| `POST /api/method/token/refresh` (`refresh`) | `{"message": {"access", "refresh"}}` |
| `POST /api/method/logout` | `{"message": {"message": "Logged Out"}}` |
| `GET /api/method/frappe.auth.get_logged_user` | `{"message": "user@example.com"}` |

Implemented in `backend/frappe_core/api/auth.py`; covered by `backend/tests/test_auth.py`.

## Deliberate omissions

- **No CSRF token handling.** It protected cookie auth; there are no cookies now.
- **`logout` does not revoke the access token.** With stateless JWTs it stays valid
  until it expires (60 min by default, `JWT_ACCESS_TOKEN_LIFETIME_MINUTES`). Add
  `rest_framework_simplejwt.token_blacklist` if that window is unacceptable - the
  backend already calls `.blacklist()` when the app is installed.

## Not done in phase 0

This SPA has **no login page** - upstream redirects to the Frappe desk's
(`session.js:35`, `window.location.href = '/login?redirect-to=/crm'`). Something has to
serve that page and call `login`, and it is not in any phase 0-4 spec. Flagged in
`PROGRESS.md`.

Concurrent 401s collapse into a single refresh (`refreshInFlight`), because a list
screen can fire a dozen requests at once and each must not spend a refresh token.
