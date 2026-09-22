# Recipe Box API

FastAPI + MongoDB backend for the Recipe Box app. JWT auth with rotating,
revocable refresh tokens, Google OAuth, email verification, recipes,
favorites, reviews, a follow/social graph, and FCM push notifications.

## Stack

- **FastAPI** (async) + **MongoDB** via **Beanie** (Motor under the hood)
- **python-jose** — JWT access tokens
- **passlib[bcrypt]** — password hashing
- **google-auth** — verifies Google Sign-In ID tokens server-side
- **firebase-admin** — sends FCM push notifications

## Run it

```bash
docker compose up --build
```
API at http://localhost:8000, docs at http://localhost:8000/docs.

Without Docker:
```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in what you need — see below
uvicorn app.main:app --reload
```

Every new feature below is **safe to leave unconfigured** — the app runs
and every unrelated endpoint works fine with zero setup. Each falls back
to a harmless dev-friendly default until you configure it for real.

---

## What's new in this version

### 1. Public profile tabs (previously missing entirely)
| Method | Path | Description |
|---|---|---|
| GET | `/users/{id}/recipes` | Recipes by this person — powers the "Recipes" tab on someone else's profile |
| GET | `/users/{id}/reviews` | Reviews *written by* this person, across every recipe (each includes which recipe it was for) — powers their "Reviews" tab |

These are distinct from `GET /recipes/{id}/reviews`, which is reviews *on* one recipe, written by anyone.

### 2. FCM push notifications
| Method | Path | Description |
|---|---|---|
| POST | `/notifications/register-device` | Register an FCM token for the current user (call after Firebase hands your app a token, and again if it rotates) |
| DELETE | `/notifications/register-device` | Unregister a token (call on logout) |

Two events currently trigger a push, both fire-and-forget (they never fail the request that triggered them):
- **New follower** — fires from `POST /users/{id}/follow`
- **New review** — fires from `POST /recipes/{id}/reviews`, notifying the recipe's author (skipped if you review your own recipe)

**Setup:** In Firebase Console → Project Settings → Service Accounts, generate a private key (a JSON file). Set `FCM_SERVICE_ACCOUNT_PATH` to its path. Until you do, sends are logged (`[FCM disabled] Would notify...`) instead of erroring — device registration itself works regardless.

Dead tokens (uninstalled app, expired registration) are automatically deleted when Firebase reports them as `NOT_FOUND`/`UNREGISTERED`.

### 3. Email verification
| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/auth/resend-verification` | required | Re-sends the verification email to the current user |
| POST | `/auth/verify-email` | – | `{token}` → marks the account verified |

Every new password-based registration gets a verification email automatically. The token is a random opaque string (same hashed-storage pattern as refresh tokens — the raw value only ever exists in the email link, never at rest in the DB) and expires after `EMAIL_VERIFICATION_EXPIRE_HOURS` (default 24).

**`EMAIL_BACKEND=console` (default):** the email is just logged to the server console, e.g. during local dev — copy the link straight out of the log.
**`EMAIL_BACKEND=smtp`:** fill in `SMTP_HOST`/`SMTP_PORT`/`SMTP_USERNAME`/`SMTP_PASSWORD` to actually send mail.

`REQUIRE_EMAIL_VERIFICATION` (default `false`): when `true`, `/auth/login` rejects unverified accounts with a 403. Off by default so you can build/test without setting up email first. Google accounts are always pre-verified (Google already confirmed the email) and are unaffected by this setting either way.

### 4. Google OAuth
| Method | Path | Description |
|---|---|---|
| POST | `/auth/google` | `{id_token}` → verifies it with Google, logs in or creates an account, returns our own `{access_token, refresh_token}` |

**How it works:** your Flutter app runs Google Sign-In natively and gets an **ID token** (not an access token) from Google. Send that ID token to this endpoint. The backend verifies its signature, expiry, and `aud` claim against `GOOGLE_CLIENT_ID` (so a token minted for a different app is rejected), then:
- If a user with that email already exists (regardless of how the account was originally created), logs them in.
- Otherwise creates a new account — no password, `auth_provider: "google"`, `is_email_verified: true` immediately (Google already verified it).

The client never sends the Google token anywhere else after this call — everything downstream uses the app's own JWT pair like any other login.

**Setup:** create an OAuth 2.0 Client ID in Google Cloud Console (one for Android, one for iOS, possibly a Web one too depending on your Flutter setup) and set `GOOGLE_CLIENT_ID` to the ID your **backend** should treat as the valid audience (typically your Web client ID, since that's what the `google_sign_in` Flutter package's server-side verification flow expects — check your specific package's docs on which client ID to use as `serverClientId`).

**Note:** verifying a Google token requires the backend to reach Google's certificate endpoint over the network (`google-auth` caches certs after the first call, so this only adds latency occasionally, not on every request).

---

## Auth flow, updated

1. `POST /auth/register` or `POST /auth/google` → `{access_token, refresh_token}`
2. `POST /auth/login` (password) → same, but blocked with 403 if `REQUIRE_EMAIL_VERIFICATION=true` and the account isn't verified yet
3. `Authorization: Bearer <access_token>` on protected requests
4. `POST /auth/refresh` with `{refresh_token}` when the access token expires — rotates both tokens
5. `POST /auth/logout` with `{refresh_token}` to revoke it server-side

## Pagination

Unchanged — every list endpoint takes `page`/`page_size` and returns `{items, total, page, page_size, pages}`.

## Full endpoint list

### Auth
| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/auth/register` | – | Register with email/password |
| POST | `/auth/login` | – | Form fields `username` (email) + `password` |
| POST | `/auth/google` | – | Google Sign-In via ID token |
| POST | `/auth/refresh` | – | Rotate token pair |
| POST | `/auth/logout` | – | Revoke a refresh token |
| POST | `/auth/resend-verification` | required | Resend verification email |
| POST | `/auth/verify-email` | – | Verify with the emailed token |
| GET | `/auth/me` | required | Current user |

### Recipes
| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/recipes` | optional | Paginated feed; `category`, `search`, `max_cook_minutes`, `sort=newest\|popular` |
| GET | `/recipes/mine` | required | Your own recipes |
| GET | `/recipes/saved` | required | Your favorited recipes |
| GET | `/recipes/{id}` | optional | Full detail |
| POST | `/recipes` | required | Create |
| PUT | `/recipes/{id}` | required (owner) | Update |
| DELETE | `/recipes/{id}` | required (owner) | Delete |
| POST | `/recipes/{id}/favorite` | required | Toggle favorite |
| GET | `/recipes/{id}/reviews` | – | Reviews on this recipe |
| POST | `/recipes/{id}/reviews` | required | Add a review (also pushes a notification to the author) |

### Users
| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/users/search` | optional | People search |
| GET | `/users/{id}` | optional | Public profile + stats |
| GET | `/users/{id}/recipes` | optional | **New** — this person's recipes |
| GET | `/users/{id}/reviews` | – | **New** — reviews written by this person |
| PUT | `/users/me` | required | Update your own profile |
| POST | `/users/{id}/follow` | required | Toggle follow (also pushes a notification) |
| GET | `/users/{id}/followers` | optional | Paginated followers |
| GET | `/users/{id}/following` | optional | Paginated following |

### Notifications
| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/notifications/register-device` | required | Register an FCM token |
| DELETE | `/notifications/register-device` | required | Unregister an FCM token |

## Project layout

```
app/
  main.py             FastAPI app, CORS, Mongo + Firebase lifespan
  config.py           Settings from .env
  database.py         Motor client, Beanie init, Firebase Admin init
  models.py           User, RefreshToken, EmailVerificationToken, DeviceToken, Recipe, Favorite, Review, Follow
  schemas.py          Pydantic request/response models + generic Page[T]
  security.py         Password hashing, JWT access tokens, opaque hashed tokens (refresh + email verification)
  email_service.py    Console/SMTP email sending
  notifications.py    FCM device registration + sending
  serializers.py       Author/recipe stitching helpers (no joins in Mongo), username generation
  dependencies.py     get_current_user (async), pagination params
  routers/
    auth.py
    recipes.py
    users.py
    notifications.py
```
