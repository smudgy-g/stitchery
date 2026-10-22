# Plan: public gallery + deployment

Status: proposed, 2026-10-20. Nothing here is built yet.

## Goal
People sign in, publish designs they generated, and anyone can browse a gallery, open a design,
see the stitch preview and download it in any machine format. Hosted at
`stitchery.adamgriff.dev` on a DigitalOcean Droplet.

## Decisions
| Area | Choice | Why |
|---|---|---|
| Region | Sydney for everything: DO `SYD1` (Droplet + Spaces), Neon `aws-ap-southeast-2` | Users are in Australia; app, DB and files share a city. Neon's region can't be changed after creation |
| Host | DigitalOcean Droplet, 2 GB RAM + 2 GB swap | Cheapest box that fits measured peak (~2 GB with background removal); we own maintenance |
| Domain | `stitchery.adamgriff.dev`, A record in Vercel DNS | `adamgriff.dev` nameservers are `ns1/ns2.vercel-dns.com`; the main site is untouched |
| One origin | Caddy serves the client and proxies `/api/*` to FastAPI | No CORS in production, auth stays same-site, one TLS cert (automatic) |
| Database | Neon Postgres (AWS region near the Droplet) | Managed, branchable, holds Neon Auth's users too |
| Auth | Neon Auth (managed Better Auth) | Hosted auth server, so the Python backend only verifies JWTs. Free tier: 60k MAU. SDK is `0.6.0-beta` |
| Files | DigitalOcean Spaces (S3 API, `boto3`) | Gallery thumbnails shouldn't stream through the DB; ~$5/mo for 250 GB |
| Stored per design | PES (private) + PNG thumbnail (public via Spaces CDN) + metadata row | Preview JSON and other formats are derived from the PES on request |
| Not stored | The user's original upload | Privacy; add only if "re-generate with new settings" is wanted |

## Architecture
```
browser ──https──> Caddy (Droplet) ──/api/*──> FastAPI + Ink/Stitch (Docker)
                     │                            ├── Neon Postgres (designs, reports, neon_auth.*)
                     └── static client build      └── Spaces (designs/{id}.pes, thumbs/{id}.png)
browser ──────────> Neon Auth (sign-in, issues JWT)
browser ──────────> Spaces CDN (thumbnails)
```

## Data model (`server/migrations/001_init.sql`)
```sql
create table designs (
  id            uuid primary key default gen_random_uuid(),
  owner_id      uuid references neon_auth."user"(id) on delete cascade,  -- null while an anonymous draft
  draft_secret  text,                       -- proves the generator owns the draft; cleared on publish
  status        text not null default 'draft' check (status in ('draft', 'public', 'hidden')),
  title         text check (char_length(title) between 1 and 80),
  machine_key   text not null,
  format        text not null,
  threads       jsonb not null,
  stitch_count  int  not null,
  width_mm      real not null,
  height_mm     real not null,
  created_at    timestamptz not null default now(),
  published_at  timestamptz
);
create index on designs (published_at desc) where status = 'public';
create index on designs (created_at) where status = 'draft';

create table reports (
  design_id   uuid references designs(id) on delete cascade,
  reporter_id uuid references neon_auth."user"(id) on delete cascade,
  reason      text not null check (char_length(reason) <= 500),
  created_at  timestamptz not null default now(),
  primary key (design_id, reporter_id)
);
```
Users come from Neon Auth's `neon_auth."user"` table (same database), so there's no users table of our own.
Migrations: plain numbered SQL files plus a ~20-line runner with a `schema_migrations` table, run on deploy.
Alembic only if migrations get complex.

## Flows
**Generate (anyone):** `POST /api/upload` works as today, and also writes the PES and thumbnail
(`pystitch.write_png`) to Spaces and inserts a `draft` row. The response adds `{id, draft_secret}`.

**Publish (signed in):** `POST /api/designs/{id}/publish {title, draft_secret}` with the Bearer JWT.
The server checks the secret, sets `owner_id`, `status='public'` and `published_at`, and clears the secret.
The secret stops someone publishing a draft they didn't generate. The client must never upload the PES itself.

**Cleanup:** a cron on the Droplet runs `docker compose exec api python -m app.cleanup` hourly.
It deletes drafts older than 24 h, along with their Spaces objects.

**Auth on the server:** a FastAPI dependency verifies `Authorization: Bearer <jwt>` with
`PyJWT` + `PyJWKClient(NEON_AUTH_JWKS_URL)`, checking signature, `exp` and audience/issuer, then uses `sub` as
the user id. The client gets the JWT from the Neon Auth SDK (`session.access_token`).

## API
| Method | Path | Who |
|---|---|---|
| GET | `/api/machines` | anyone (exists) |
| POST | `/api/upload` | anyone (exists; now also creates a draft) |
| POST | `/api/designs/{id}/publish` | signed in + draft secret |
| GET | `/api/designs?cursor=` | anyone; public only, newest first, 24 per page |
| GET | `/api/designs/{id}` | anyone if public, owner otherwise; returns metadata + preview blocks parsed from the PES |
| GET | `/api/designs/{id}/file?format=jef` | same as above; converts with the existing `pystitch.write_*` code |
| DELETE | `/api/designs/{id}` | owner or admin |
| POST | `/api/designs/{id}/report` | signed in |
| POST | `/api/designs/{id}/hide` | admin (`ADMIN_USER_IDS` env) |

Thumbnails are linked straight to the Spaces CDN URL and don't go through the API.

## Client
- Add `react-router` with three pages: `/` studio (today's page), `/gallery`, `/designs/:id`.
- Neon Auth: `@neondatabase/auth` client plus its React UI provider for sign-in/up and the user menu.
- After generating: "Publish to gallery" (title field; prompts sign-in when signed out).
- Detail page: reuse `StitchPreview`, thread list, machine/format picker for download, report button.
- `VITE_API_URL` becomes the relative `/api` in production. Dev keeps the Vite proxy or the full URL.

## Abuse and moderation (before going public)
- Publish rate limit: 20 per user per day (a count query; no new infrastructure).
- Generate is the expensive endpoint (~2 GB RAM, 5–20 s). A process-wide semaphore runs one generation at a
  time and queues the rest, plus a per-IP limit in Caddy. Without this, two concurrent background-removal
  requests can exhaust memory on a 2 GB box.
- Report button, an admin hide endpoint, and a short terms line at publish ("you own the rights to this artwork").

## Deployment (`deploy/`)
- `deploy/setup.sh`, run once on a fresh Ubuntu LTS Droplet: Docker, `ufw` (22/80/443), unattended-upgrades,
  2 GB swap, a deploy user with SSH key only, and the cleanup cron.
- `deploy/compose.yml` has two services, each with `restart: unless-stopped`:
  - `api`: `ghcr.io/smudgy-g/stitchery-api`, the existing server Dockerfile, reading `/srv/stitchery/.env`
  - `web`: `ghcr.io/smudgy-g/stitchery-web`, Caddy plus the built client and the `Caddyfile`
- `deploy/Caddyfile`:
  ```
  stitchery.adamgriff.dev {
      encode gzip
      handle_path /api/* { reverse_proxy api:8000 }
      handle { root * /srv/client; try_files {path} /index.html; file_server }
  }
  ```
- `.github/workflows/deploy.yml` runs on push to `main`. It runs server tests in the built image, builds both
  images, and pushes them to GHCR. Then it SSHes to the Droplet to run `docker compose pull`, run migrations,
  `docker compose up -d`, and `docker image prune -f`. Images are built in CI and never on the 2 GB Droplet.
- Secrets:
  - GitHub: `DROPLET_HOST`, `DROPLET_SSH_KEY`
  - Droplet `.env`: `DATABASE_URL`, `NEON_AUTH_JWKS_URL`, `SPACES_KEY`, `SPACES_SECRET`, `SPACES_BUCKET`,
    `SPACES_REGION`, `ADMIN_USER_IDS`
- DNS: in Vercel → Domains → adamgriff.dev, add an `A` record `stitchery` → Droplet IP
  (or `vercel dns add adamgriff.dev stitchery A <ip>`). Caddy issues the certificate on first request.
- The Droplet keeps no state: DB on Neon, files on Spaces. Recovery means a new Droplet, `setup.sh`, the
  `.env`, then a re-deploy.

## Phases (each ends deployable)
1. **Spike (~1 h).** Create the Neon project with Neon Auth. Find the JWKS URL and token audience/issuer.
   Verify a real token from Python. *Done when:* a script prints `sub` from a token minted by the Vite client.
2. **Deploy today's app.** `deploy/`, workflow, DNS, Droplet. *Done when:*
   `https://stitchery.adamgriff.dev` generates a design end to end and a push to `main` redeploys.
3. **Storage + drafts.** Migrations, Spaces, draft rows on generate, cleanup. *Done when:* generating creates a
   row plus two objects, and a 25 h old draft disappears after cleanup.
4. **Gallery (read-only).** List/detail/file endpoints and pages, with a temporary admin-only publish.
   *Done when:* your own published design shows in `/gallery` and downloads as JEF/DST.
5. **Sign-in + publish.** Neon Auth in the client, the JWT dependency, the publish flow with draft secret.
   *Done when:* a second account can publish, can't publish someone else's draft (403), and can't delete
   others' designs.
6. **Moderation + limits.** Report, hide, rate limits, generation semaphore, terms line. Then share the link.

Tests per phase follow the existing `tests/` style (unittest + TestClient). Spaces is faked with
`moto` or a patched client. DB tests run against a Neon branch, or a local Postgres in Docker in CI.

## Open decisions
- **Droplet size:** 2 GB + swap with one generation at a time, or 4 GB to allow two at once.
- **Smaller background-removal model:** if `u2netp` quality is acceptable, peak RAM drops to ~600 MB.
- **Anonymous generation:** stays open (current behaviour); only publishing needs sign-in.
