# Plan: public gallery + deployment

Status: proposed, updated 2026-11-27. The deploy pipeline exists (single image, Droplet + Caddy);
the gallery, sign-in and storage are not built yet.

## Goal
People sign in, publish designs they generated, and anyone can browse a gallery, open a design,
see the stitch preview and download it in any machine format. Hosted at
`stitchery.adamgriff.dev`. Users are mostly in Australia (family and friends to start).

## Decisions
| Area | Choice | Why |
|---|---|---|
| Packaging | One Docker image (root `Dockerfile`): FastAPI serves the API and the built SvelteKit client | One thing to build and deploy; same origin, so no CORS and auth stays same-site |
| Host | **Open**: Railway (Hobby) or DigitalOcean Droplet. See Open decisions | The app server keeps no state, so either works and moving later is cheap |
| Domain | `stitchery.adamgriff.dev`, DNS in Vercel | `adamgriff.dev` nameservers are `ns1/ns2.vercel-dns.com`; the main site is untouched. Droplet: `A` record. Railway: `CNAME` to the Railway domain |
| HTTPS | The host's (Railway), or Caddy (stock image + `deploy/Caddyfile`) on a Droplet | The image itself serves plain HTTP on `$PORT` (default 8000) |
| Database | Neon Postgres, region `aws-ap-southeast-2` (Sydney) | Managed, branchable, holds Neon Auth's users too. Region can't change after creation |
| Auth | Neon Auth (managed Better Auth) | Hosted auth server, so the Python backend only verifies JWTs. Free tier: 60k MAU |
| Files | S3-compatible bucket: DO Spaces (SYD1) or Railway object storage | Thumbnails shouldn't stream through the DB. Same `boto3` code either way |
| Stored per design | Machine file (private) + PNG thumbnail (public) + metadata row | Preview and other formats are derived from the stored file on request |
| Not stored | The user's original upload | Privacy; add only if "re-generate with new settings" is wanted |

## Architecture
```
browser ──https──> [host HTTPS | Caddy] ──> one container: FastAPI + Ink/Stitch + built client
                                              ├── Neon Postgres (designs, reports, neon_auth.*)
                                              └── bucket (designs/{id}.pes, thumbs/{id}.png)
browser ──────────> Neon Auth (sign-in, issues JWT)
browser ──────────> bucket CDN / public URL (thumbnails)
```

## Measured resource use
Current image, koala sample, 10 colours, 90 mm, squiggle fill, after one background removal:
peak ~1.0 GB (container cgroup, includes page cache), ~0.9 GB idle once the background-removal
model is loaded. Background removal ~1 s and that stitch ~19 s on a 16-core dev machine; expect slower
on one shared vCPU. 2 GB of RAM is enough for one generation at a time.

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
Migrations: plain numbered SQL files plus a ~20-line runner with a `schema_migrations` table, run at
container start (works on any host). Alembic only if migrations get complex.

## Routing (do this first, in phase 3)
Today the API lives at the root (`/machines`, `/threads`, `/remove-background`, `/colours`, `/stitch`)
and `StaticFiles` serves the client at `/`. Before adding pages:
- **Move the API under `/api`** (an `APIRouter(prefix="/api")`; the client's `API_URL` becomes `/api`
  in the image, `http://127.0.0.1:8000/api` in dev). Otherwise page paths like `/designs/{id}` collide
  with API paths.
- **SPA fallback:** `StaticFiles(html=True)` only serves `index.html` at `/`. Deep links such as
  `/gallery` need a catch-all that returns `index.html` for unknown non-`/api` GETs (SvelteKit's
  `adapter-static` already builds with `fallback: "index.html"`).

## Flows
**Generate (anyone):** `POST /api/stitch` works as today, and also writes the machine file and a thumbnail
(`pystitch.write_png`) to the bucket and inserts a `draft` row. The response adds `{id, draft_secret}`.

**Publish (signed in):** `POST /api/designs/{id}/publish {title, draft_secret}` with the Bearer JWT.
The server checks the secret, sets `owner_id`, `status='public'` and `published_at`, and clears the secret.
The secret stops someone publishing a draft they didn't generate. The client must never upload the file itself.

**Cleanup:** deletes drafts older than 24 h with their bucket objects (`python -m app.cleanup`).
Railway: a cron service running the same image. Droplet: a host cron running `docker compose exec app ...`.

**Auth on the server:** a FastAPI dependency verifies `Authorization: Bearer <jwt>` with
`PyJWT` + `PyJWKClient(NEON_AUTH_JWKS_URL)`, checking signature, `exp` and audience/issuer, then uses `sub` as
the user id.

## API
| Method | Path | Who |
|---|---|---|
| GET | `/api/machines`, `/api/threads` | anyone (exist, move under `/api`) |
| POST | `/api/remove-background`, `/api/colours` | anyone (exist, move under `/api`) |
| POST | `/api/stitch` | anyone (exists; now also creates a draft) |
| POST | `/api/designs/{id}/publish` | signed in + draft secret |
| GET | `/api/designs?cursor=` | anyone; public only, newest first, 24 per page |
| GET | `/api/designs/{id}` | anyone if public, owner otherwise; metadata + preview blocks parsed from the file |
| GET | `/api/designs/{id}/file?format=jef` | same as above; converts with the existing `pystitch.write_*` code |
| DELETE | `/api/designs/{id}` | owner or admin |
| POST | `/api/designs/{id}/report` | signed in |
| POST | `/api/designs/{id}/hide` | admin (`ADMIN_USER_IDS` env) |

## Client (SvelteKit, `adapter-static`)
- Routes: `src/routes/+page.svelte` (studio, exists), `src/routes/gallery/+page.svelte`,
  `src/routes/designs/[id]/+page.svelte`.
- Neon Auth: check whether its SDK has a framework-free client. Its ready-made sign-in UI is React, so
  expect to build a small Svelte sign-in form and user menu on the client API.
- After generating: "Publish to gallery" (title field; prompts sign-in when signed out).
- Detail page: reuse `StitchPreview` and `HoopFrame`, the thread list, a machine/format picker for
  download, and a report button.

## Abuse and moderation (before sharing widely)
- Generation already runs one at a time (`GENERATION_LOCK`) and uploads are capped at 20 MB in the app.
- Publish rate limit: 20 per user per day (a count query; no new infrastructure).
- Generate is the expensive endpoint. Add a per-IP limit in the app (works on any host; Caddy only exists
  on a Droplet). On Railway, also set a monthly spending limit, since CPU is billed by use.
- Report button, an admin hide endpoint, and a short terms line at publish ("you own the rights to this artwork").

## Deployment
**What exists:** the root `Dockerfile` (client build + API + Ink/Stitch + baked background-removal model),
and `.github/workflows/deploy.yml`, which on push to `main` builds the image, runs the server tests inside
it, pushes `ghcr.io/smudgy-g/stitchery` to GHCR and redeploys the Droplet over SSH with
`deploy/compose.yml` (`app` + stock `caddy:2-alpine`) and `deploy/Caddyfile`.
`deploy/setup.sh` prepares a fresh Ubuntu Droplet (Docker, `ufw`, unattended-upgrades, 2 GB swap,
deploy user).

**If Railway:** connect the repo; Railway builds the root `Dockerfile` and sets `PORT`. Remove the
Droplet job from the workflow (keep build + test as CI) and delete `deploy/`. Secrets go in Railway's
service variables.

**Secrets (either host):** `DATABASE_URL`, `NEON_AUTH_JWKS_URL`, bucket key/secret/name/region,
`ADMIN_USER_IDS`. Droplet: in `/srv/stitchery/.env`; GitHub also holds `DROPLET_HOST`,
`DROPLET_SSH_KEY`, `DROPLET_HOST_KEY`.

The app server keeps no state: DB on Neon, files in the bucket. Recovery is a redeploy.

## Phases (each ends deployable)
1. **Spike (~1 h).** Create the Neon project with Neon Auth. Find the JWKS URL and token audience/issuer.
   Verify a real token from Python. *Done when:* a script prints `sub` from a token minted by the client.
2. **Deploy today's app.** Pick the host, point DNS at it. *Done when:*
   `https://stitchery.adamgriff.dev` generates a design end to end and a push to `main` redeploys.
3. **Routing + storage + drafts.** API under `/api`, SPA fallback, migrations, bucket, draft rows on
   generate, cleanup. *Done when:* generating creates a row plus two objects, and a 25 h old draft
   disappears after cleanup.
4. **Gallery (read-only).** List/detail/file endpoints and pages, with a temporary admin-only publish.
   *Done when:* your own published design shows in `/gallery` and downloads as JEF/DST.
5. **Sign-in + publish.** Neon Auth in the client, the JWT dependency, the publish flow with draft secret.
   *Done when:* a second account can publish, can't publish someone else's draft (403), and can't delete
   others' designs.
6. **Moderation + limits.** Report, hide, rate limits, terms line. Then share the link.

Tests per phase follow the existing `server/tests/` style (unittest + TestClient). The bucket is faked with
`moto` or a patched client. DB tests run against a Neon branch, or a local Postgres in Docker in CI.

## Open decisions
- **Host:** Railway Hobby (~$10–12/mo estimated from usage rates, HTTPS and deploys built in, nothing to
  maintain, cost grows with CPU use; check for a region near Australia, last known nearest was Singapore)
  or a DigitalOcean Droplet in SYD1 ($12/mo fixed for 1 vCPU / 2 GB, you maintain Ubuntu and Caddy).
- **Bucket:** DO Spaces (SYD1, ~$5/mo for 250 GB) or Railway object storage (~$0.015/GB-month, free egress).
- **Two generations at once:** needs ~4 GB RAM and replacing the lock with a small semaphore.
- **Smaller background-removal model:** if `u2netp` quality is acceptable, memory drops further.
- **Anonymous generation:** stays open (current behaviour); only publishing needs sign-in.
