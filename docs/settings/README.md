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

## Personal profile contract

- `GET /api/v1/profile` creates and returns one `user_profiles` row for the authenticated Better Auth user ID. The initial avatar is selected from the current five-image set (`avatar-01` through `avatar-05`) and persisted; more built-in avatars can be added later without changing ownership rules.
- `PATCH /api/v1/profile` partially updates the built-in avatar choice, short bio, achievements, education history, biography, and institution history. The request body cannot select a user ID.
- Structured list items are validated by Pydantic; unknown fields, invalid years, overlong values, and non-allowlisted avatar keys are rejected.
- Profile data lives in the FastAPI business database and is not an authentication source. Better Auth remains the sole owner of users, credentials, and sessions.
- The settings UI clears profile state when the authenticated user changes. A failed save keeps the browser draft available for retry.

## Account management (phase three)

The **Account** block on `/settings?tab=profile` manages authentication data only. It does **not** add FastAPI routes or read Better Auth tables from the business backend.

| Capability | Boundary | Notes |
| --- | --- | --- |
| Email display | Better Auth session | Read-only |
| Display name | `authClient.updateUser` | Shared browser/server policy trims the value, rejects blank names, and caps names at 80 characters |
| Change password | `authClient.changePassword` | Revokes other sessions on success |
| Set initial password (OAuth) | `/api/auth/password/send-otp` + `/api/auth/password/set` | Email OTP proves mailbox ownership |
| Session list / revoke others | `listSessions` / `revokeOtherSessions` | Better Auth session store; stale sensitive sessions reauthenticate and verify that the user did not switch accounts before retrying |
| Change email | `authClient.changeEmail` | Better Auth verifies the current mailbox first, then the replacement mailbox; unavailable email delivery is reported before the request |
| Delete account | `/api/auth/account-deletion` | Trusted server orchestration: delete all current FastAPI business data first, then call Better Auth to delete the authentication account; retries are idempotent and successful deletion refreshes the browser session immediately |

Implementation layout:

- UI: `features/settings/components/account-section.tsx`, `account-sessions.tsx`
- Orchestration: `features/settings/services/account-password.ts` (OTP set-password only)
- Copy: `features/settings/i18n.ts` (`accountMessages`)

Out of scope for this phase:

- FastAPI account APIs or business-database credential storage
- Avatar upload and scholar profile fields (phase two `user_profiles`)
- Retaining any user profile, preference, or Chat history after an approved account deletion

## Dependency and route boundaries

- `clients/backend/*` is the browser client boundary for FastAPI business APIs such as settings and profile. It does not own authentication and must not import Feature/UI code.
- `lib/auth/*` is server-side Better Auth configuration, security policy, and email infrastructure. It does not import `clients`; Feature components may depend on both boundaries, but the boundaries never depend on each other.
- `/api/auth/[...all]` remains the sole Better Auth HTTP handler for its official endpoints. `/api/auth/password/*` is deliberately narrower: Better Auth's initial `setPassword` endpoint is server-only, while the product needs an authenticated mailbox-OTP proof and OAuth placeholder-credential handling. The browser calls `features/settings/services/account-password.ts`; that service holds no secret and cannot access the Adapter.
- Account deletion is the one cross-database orchestration: the browser calls `/api/auth/account-deletion`, which derives identity from its Better Auth session, marks the internal FastAPI cleanup request, deletes `user_profiles`, `user_settings`, and `user:*` Chat sessions/messages in one `CHAT_DATABASE_URL` transaction, then deletes Better Auth authentication data. A cleanup retry returning zero deleted rows is successful and can complete a previously failed final Auth deletion.
- Better Auth database hooks remove the user-bound `set-password-otp:<userId>` verification before deleting the user. The `verification` table has no user foreign key, so this ShenZhi-owned challenge cannot rely on the `user` cascade used by `account` and `session`.
- Account actions keep independent pending and feedback state. Deletion failures retain the response request ID so operators can correlate the UI error with server logs.

Known production boundary: Chat generation cancellation currently reaches only the Backend worker handling the deletion request. A multi-worker deployment still needs distributed cancellation. Account deletion is synchronous and idempotent, but it does not yet use a durable deletion-job table or background retry/alert workflow.
