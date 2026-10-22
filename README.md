## To build Dockerfile

```
docker build \
--progress=plain \
-t embroidery-server:inkstitch-3.2.2 \
./server


## To run Dockerfile
```

docker run --rm \
--name embroidery-server \
-p 8000:8000 \
embroidery-server:inkstitch-3.2.2

```

```

```

```

## Deploy (stitchery.adamgriff.dev)

Pushing to `main` builds and tests both images in GitHub Actions, pushes them to GHCR, and restarts
them on the Droplet (`.github/workflows/deploy.yml`). Caddy serves the client and forwards `/api/*`
to the server, with HTTPS set up automatically.

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
- Logs: `docker compose logs -f api`
- Roll back: `IMAGE_TAG=<older commit sha> docker compose up -d`
  (re-run the workflow for that commit if the image needs pulling again)

Test the production setup locally on http://localhost:8088. Build both images with the deploy tags, then run:
`docker build -t ghcr.io/smudgy-g/stitchery-api ./server && docker build -f deploy/web.Dockerfile -t ghcr.io/smudgy-g/stitchery-web .`
then start with `SITE_ADDRESS=:80` and port 8088 mapped to 80.
