# Personal settings foundation

The settings module follows `Page -> Feature -> Client -> generic Next.js BFF -> FastAPI -> Service -> PostgreSQL`.

## API contract

- `GET /api/v1/settings` returns the authenticated user's `locale`, `theme_mode`, four notification preferences, and timestamps.
- `PATCH /api/v1/settings` accepts a partial top-level update. Allowed values are `locale: "zh-CN" | "en"`, `theme_mode: "light" | "dark" | "system"`, and a complete `notifications` object.
- The FastAPI boundary derives `user_id` from the trusted BFF identity headers. Anonymous callers receive `401`; request bodies cannot select another user.

## Persistence and fallback

Run `uv run alembic -c alembic.ini upgrade head` from `apps/backend` with `CHAT_DATABASE_URL` configured. Migration `003_user_settings` creates one row per Better Auth user ID, with server defaults and timestamps.

Signed-in users use server preferences as the source of truth. Theme and locale remain browser-local while signed out. If a signed-in save fails, the optimistic change is rolled back and the existing local theme remains usable.

Notification values currently record preference only. No delivery channel, inbox, or push capability is claimed in this phase.
