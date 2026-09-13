# Recipe Box API (MongoDB edition)

FastAPI backend for the Recipe Box app, backed by **MongoDB** via
**Beanie** (an async ODM on top of Motor). JWT access tokens, **DB-backed
rotating refresh tokens**, favorites, reviews, follows, and pagination
on every list endpoint.

## Stack

- **FastAPI** — routing, validation, OpenAPI docs (all async)
- **MongoDB** via **Beanie** (Motor under the hood)
- **python-jose** — JWT access tokens
- **passlib[bcrypt]** — password hashing

## Run it (Docker — easiest)

```bash
docker compose up --build
```

Starts MongoDB and the API together.
- API: http://localhost:8000
- Interactive docs: http://localhost:8000/docs

## Run it locally (without Docker)

```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env            # edit MONGO_URI / SECRET_KEY as needed
# make sure MongoDB is running (e.g. `mongod` locally, or a free Atlas cluster)

uvicorn app.main:app --reload
```

Beanie initializes collections and indexes automatically on startup —
no migrations step needed, since MongoDB is schemaless (indexes are
still declared explicitly in `app/models.py` for uniqueness/perf).

## Data model

Documents (collections) — see `app/models.py`:

- **users** — profile fields + hashed password
- **refresh_tokens** — see below
- **recipes** — `ingredients` and `steps` are embedded string arrays
  directly on the recipe document (no separate collection/join — this
  is the natural Mongo shape, unlike the old relational version)
- **favorites** — `{user_id, recipe_id}` pairs
- **reviews** — `{recipe_id, author_id, rating, comment}`, one per user
  per recipe; posting one updates the recipe's running `rating_avg`
- **follows** — `{follower_id, followed_id}` pairs

There are no joins in Mongo, so list endpoints batch-fetch the
authors/users they need in a second query and stitch them onto the
response in Python (see `app/serializers.py`) rather than relying on
`SELECT ... JOIN`.

## Refresh tokens — how this one actually works

This is a **real, revocable refresh token system**, not just a second
JWT:

- **Access tokens** are still short-lived JWTs (30 min default) —
  stateless, no DB hit needed to validate one.
- **Refresh tokens** are random opaque strings (`secrets.token_urlsafe`).
  The raw value is only ever shown to the client once, at issue time.
  The server stores **only a SHA-256 hash** of it in the
  `refresh_tokens` collection, alongside `user_id`, `expires_at`, and a
  `revoked` flag.
- **Rotation**: every call to `/auth/refresh` marks the token used to
  make that call as `revoked` and issues a brand-new access+refresh
  pair. A refresh token can only ever be used once. If someone replays
  an old, already-rotated token, the request is rejected — that's a
  signal it may have leaked.
- **Logout**: `/auth/logout` explicitly revokes a refresh token, so a
  device can be signed out server-side, not just by deleting the token
  on the client.

Because the DB is checked on every refresh, refresh tokens are fully
revocable — unlike a pure-JWT refresh design, there's no way to keep
using a refresh token after the server has invalidated it.

## Pagination

Every list endpoint takes `page` (default 1) and `page_size` (default
10, max 100) and returns:

```json
{ "items": [...], "total": 42, "page": 1, "page_size": 10, "pages": 5 }
```

## Endpoints

### Auth
| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/auth/register` | – | Create account → `{access_token, refresh_token}` |
| POST | `/auth/login` | – | Form fields `username` (email) + `password` → tokens |
| POST | `/auth/refresh` | – | `{refresh_token}` → new, rotated token pair |
| POST | `/auth/logout` | – | `{refresh_token}` → revokes it |
| GET | `/auth/me` | required | Current user |

### Recipes
| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/recipes` | optional | Paginated feed; filter by `category`, `search`, `max_cook_minutes`; `sort=newest\|popular` |
| GET | `/recipes/mine` | required | Your own recipes, paginated |
| GET | `/recipes/saved` | required | Your favorited recipes, paginated |
| GET | `/recipes/{id}` | optional | Full detail incl. ingredients/steps |
| POST | `/recipes` | required | Create a recipe |
| PUT | `/recipes/{id}` | required (owner) | Update a recipe |
| DELETE | `/recipes/{id}` | required (owner) | Delete a recipe |
| POST | `/recipes/{id}/favorite` | required | Toggle favorite → `{is_favorite}` |
| GET | `/recipes/{id}/reviews` | – | Paginated reviews |
| POST | `/recipes/{id}/reviews` | required | Add a review (1 per user per recipe) |

### Users
| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/users/search` | optional | People search — matches `full_name` or `username`; powers the People tab |
| GET | `/users/{id}` | optional | Public profile + stats |
| PUT | `/users/me` | required | Update your own profile |
| POST | `/users/{id}/follow` | required | Toggle follow → `{is_following}` |
| GET | `/users/{id}/followers` | optional | Paginated followers — each includes recipe/follower counts and `is_following` relative to you |
| GET | `/users/{id}/following` | optional | Paginated following — same shape as followers |

## Example requests

```bash
# Register
curl -X POST localhost:8000/auth/register \
  -H "Content-Type: application/json" \
  -d '{"full_name":"Sam Rivera","email":"sam@example.com","password":"hunter22!!"}'

# Login
curl -X POST localhost:8000/auth/login \
  -F "username=sam@example.com" -F "password=hunter22!!"

# Refresh (rotates both tokens)
curl -X POST localhost:8000/auth/refresh \
  -H "Content-Type: application/json" \
  -d '{"refresh_token": "<the refresh token from login>"}'

# Logout (revokes the refresh token)
curl -X POST localhost:8000/auth/logout \
  -H "Content-Type: application/json" \
  -d '{"refresh_token": "<refresh token>"}'

# Create a recipe (replace $TOKEN with an access token)
curl -X POST localhost:8000/recipes \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{
        "title": "Weeknight Lemon Chicken Orzo",
        "cook_minutes": 30, "difficulty": "Easy", "category": "Dinner",
        "ingredients": ["2 chicken breasts, diced", "1 cup orzo"],
        "steps": ["Sear the chicken until golden.", "Simmer orzo in stock until tender."]
      }'

# Follow another user, then see who follows them
curl -X POST localhost:8000/users/<user_id>/follow -H "Authorization: Bearer $TOKEN"
curl "localhost:8000/users/<user_id>/followers?page=1&page_size=20"
```

## Project layout

```
app/
  main.py          FastAPI app, CORS, async Mongo lifespan
  config.py        Settings from .env (pydantic-settings)
  database.py      Motor client + Beanie init
  models.py        Beanie documents: User, RefreshToken, Recipe, Favorite, Review, Follow
  schemas.py       Pydantic request/response models + generic Page[T]
  security.py      Password hashing, JWT access tokens, opaque refresh tokens
  serializers.py   Stitches author/user info onto recipes/reviews (no joins in Mongo)
  dependencies.py  get_current_user (async), pagination params
  routers/
    auth.py
    recipes.py
    users.py
```

## Connecting the Flutter app

Point the app at `http://<your-host>:8000`. Store both tokens (e.g. via
`flutter_secure_storage`) after login/register. Attach the access token
as `Authorization: Bearer <token>` on every request. When a request
comes back 401, call `/auth/refresh` with the stored refresh token,
save the new pair, and retry — if `/auth/refresh` itself fails, treat
that as a real logout and send the user back to the login screen.
