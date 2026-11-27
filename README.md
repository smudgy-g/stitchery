## Run the whole site in Docker

One image holds the API and the built web app. From the repo root:

```
docker build --progress=plain -t stitchery .
docker run -d --rm --name stitchery -p 8000:8000 --env-file server/.env stitchery
```

Then open http://localhost:8000. No HTTPS needed locally; hosts that run the image (or Caddy on the
Droplet) add it. The server listens on `$PORT` if the host sets one, otherwise 8000.
`--env-file server/.env` turns on accounts (see below); leave it out if you don't have that file.
The file is never copied into the image (`.dockerignore`), so it has to be passed in like this.

The container runs the code from when it was built, so **rebuild after changing anything in
`server/`** (or in `client/`, if you use the site on port 8000):

```
docker stop stitchery        # --rm removes it once stopped, freeing the name
docker build --progress=plain -t stitchery .
docker run -d --rm --name stitchery -p 8000:8000 --env-file server/.env stitchery
```

Other handy commands: `docker logs -f stitchery` (server output), `docker ps` (is it running?).
If it was started without `--rm`, remove it with `docker rm -f stitchery` before running it again.

For client work, run `pnpm dev` in `client/` against that container (Vite forwards `/api` to
http://127.0.0.1:8000). Client changes show up straight away; server changes need the rebuild above.

## Accounts and saved designs (Neon)

Sign-in is Neon Auth and saved designs live in Neon Postgres. Without these settings the app still
works; signing in just says it isn't set up. Put them in `server/.env` (git-ignored):

```
DATABASE_URL=postgresql://...        # Neon: Connect > connection string (pooled is fine)
NEON_AUTH_BASE_URL=https://ep-....neonauth.ap-southeast-2.aws.neon.tech/neondb/auth   # Neon: Auth > Configuration
```

The run commands above already pass this file with `--env-file server/.env`. Changes to it need the
container restarted (stop and run again; no rebuild). The `designs` table is created at startup.

The browser never talks to Neon Auth directly: the server passes `/api/auth/*` through to it, so its
cookies belong to this site (Safari blocks them otherwise). Neon Auth only accepts listed sites:
localhost is allowed by default; add the production address in Neon under Auth > Domains (or
`neon neon-auth domain add https://stitchery.adamgriff.dev`).

Server tests for saved designs need a scratch Postgres:
`docker run -d --rm -p 55432:5432 -e POSTGRES_PASSWORD=test postgres:17-alpine`, then
`TEST_DATABASE_URL=postgresql://postgres:test@127.0.0.1:55432/postgres uv run python -m unittest discover -s tests`.

## Deploy (stitchery.adamgriff.dev)

Pushing to `main` builds and tests the image in GitHub Actions, pushes it to GHCR, and restarts it
on the Droplet (`.github/workflows/deploy.yml`). Caddy (the stock image, with `deploy/Caddyfile`)
sits in front for HTTPS.

One-time setup:

1. Create an Ubuntu 24.04 Droplet in **SYD1**, 2 GB RAM, with your SSH key. Then run:
   `scp deploy/setup.sh root@<ip>: && ssh root@<ip> bash setup.sh`
2. In Vercel → Domains → adamgriff.dev, add an `A` record `stitchery` → `<ip>`.
3. Make a key just for CI and allow it on the Droplet:
   `ssh-keygen -t ed25519 -N "" -f stitchery-ci` then
   `ssh-copy-id -i stitchery-ci.pub deploy@<ip>`
4. In GitHub → repo → Settings → Secrets → Actions, add:
   - `DROPLET_HOST`: `<ip>`
   - `DROPLET_SSH_KEY`: contents of `stitchery-ci` (the private key), then delete the local copy
   - `DROPLET_HOST_KEY`: output of `ssh-keyscan -t ed25519 <ip>`
5. Push to `main`, or run the workflow by hand from the Actions tab.

On the Droplet (`ssh deploy@<ip>`, `cd /srv/stitchery`):
- Logs: `docker compose logs -f app`
- Roll back: `IMAGE_TAG=<older commit sha> docker compose up -d`
  (re-run the workflow for that commit if the image needs pulling again)

Test the production setup locally: `docker build -t ghcr.io/smudgy-g/stitchery .`, then in `deploy/`
run `SITE_ADDRESS=:80 docker compose up` and open http://localhost.
