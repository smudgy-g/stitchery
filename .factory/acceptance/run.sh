#!/usr/bin/env bash
# Offline acceptance: build the pushed client from staged packages, then check it in a real
# browser under light and dark system themes. Logs to stderr; one JSON verdict on stdout.
set -euo pipefail

work=$(mktemp -d "$HOME/acceptance-XXXXXX")
trap 'rm -rf "$work"' EXIT
mkdir -p "$work/node" "$work/project" "$work/bin"

tar -xzf "$ASSETS/node-linux-x64.tar.gz" -C "$work/node" --strip-components=1
tar -xzf "$ASSETS/pnpm-11.22.0.tgz" -C "$work"
tar -xf "$PROJECT_ARCHIVE" -C "$work/project"
printf '#!/bin/sh\nexec node %s/package/bin/pnpm.cjs "$@"\n' "$work" > "$work/bin/pnpm"
chmod +x "$work/bin/pnpm"
export PATH="$work/bin:$work/node/bin:$PATH" CI=true
cp -r "$ASSETS/pnpm-store" "$work/store"
cp -r "$ASSETS/pnpm-cache" "$work/cache"

verdict() {
  node -e 'process.stdout.write(JSON.stringify({commit: process.env.COMMIT, pass: process.argv[1] === "true", detail: process.argv[2].slice(-1500) || "no detail"}) + "\n")' "$1" "$2"
  exit 0
}

cd "$work/project/client"
# Install failure means the staged packages no longer match the lockfile: a setup problem, not a verdict.
pnpm install --offline --frozen-lockfile --store-dir "$work/store" --cache-dir "$work/cache" >&2 ||
  { echo "Offline install failed: restage .factory/assets/pnpm-store for the new lockfile" >&2; exit 2; }
if ! out=$(pnpm build 2>&1); then echo "$out" >&2; verdict false "Client build failed: ${out: -1000}"; fi

docker load -i "$ASSETS/playwright-1.56.1.tar" >&2

cat > "$work/check.mjs" <<'JS'
import { createServer } from 'node:http'
import { readFile } from 'node:fs/promises'
import { createRequire } from 'node:module'
import { extname, join, normalize } from 'node:path'
const { chromium } = createRequire('/runner/')('playwright')
const types = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.svg': 'image/svg+xml',
  '.png': 'image/png', '.woff2': 'font/woff2', '.json': 'application/json' }
const server = createServer(async (req, res) => {
  const path = normalize(decodeURIComponent(new URL(req.url, 'http://x').pathname))
  if (path.startsWith('/api/')) { res.writeHead(404, { 'content-type': 'application/json' }); return res.end('{}') }
  const file = await readFile(join('/site', path)).catch(() => null) ?? await readFile('/site/index.html')
  res.writeHead(200, { 'content-type': types[extname(path)] ?? 'text/html' }); res.end(file)
}).listen(4173)

const browser = await chromium.launch().catch(e => { console.error(e); process.exit(2) })
// Resolve any CSS colour (oklch included) to RGB by painting it.
const colours = page => page.evaluate(() => {
  const rgb = c => { const x = document.createElement('canvas').getContext('2d'); x.fillStyle = c; x.fillRect(0, 0, 1, 1); return [...x.getImageData(0, 0, 1, 1).data.slice(0, 3)] }
  const s = getComputedStyle(document.body)
  return { bg: rgb(s.backgroundColor), fg: rgb(s.color) }
})
const lum = ([r, g, b]) => [r, g, b].map(v => { v /= 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4 })
  .reduce((sum, v, i) => sum + v * [0.2126, 0.7152, 0.0722][i], 0)
const contrast = (a, b) => { const [hi, lo] = [lum(a), lum(b)].sort((x, y) => y - x); return (hi + 0.05) / (lo + 0.05) }
const failures = []
const expect = (ok, what) => { if (!ok) failures.push(what) }

const open = async scheme => { const page = await browser.newPage({ colorScheme: scheme }); await page.goto('http://localhost:4173/'); await page.waitForLoadState('networkidle'); return page }

const light = await colours(await open('light'))
expect(light.bg.join() === '245,238,232', `light: background is rgb(${light.bg}), not the existing paper rgb(245,238,232)`)
expect(contrast(light.bg, light.fg) >= 4.5, `light: text contrast ${contrast(light.bg, light.fg).toFixed(1)} < 4.5`)

const dark = await colours(await open('dark'))
expect(lum(dark.bg) < 0.2, `dark: background rgb(${dark.bg}) is not dark`)
expect(contrast(dark.bg, dark.fg) >= 4.5, `dark: text contrast ${contrast(dark.bg, dark.fg).toFixed(1)} < 4.5`)

const live = await open('light')
await live.evaluate(() => { window.__noReload = true })
await live.emulateMedia({ colorScheme: 'dark' })
await live.waitForTimeout(1000)
const switched = await colours(live)
expect(await live.evaluate(() => window.__noReload === true), 'live: the page reloaded on theme change')
expect(lum(switched.bg) < 0.2, `live: background stayed rgb(${switched.bg}) after switching to dark`)

await browser.close(); server.close()
console.log(failures.length ? failures.join('; ') : 'Light keeps the existing palette; dark is dark and readable; live switch works without reload')
process.exit(failures.length ? 1 : 0)
JS

set +e
out=$(docker run --rm --network none --ipc=host -v "$work/project/client/build:/site:ro" \
  -v "$ASSETS/runner:/runner:ro" -v "$work/check.mjs:/check.mjs:ro" \
  mcr.microsoft.com/playwright:v1.56.1-noble node /check.mjs 2>&2)
code=$?
set -e
echo "$out" >&2
case $code in
  0) verdict true "$out" ;;
  1) verdict false "$out" ;;
  *) echo "Browser check could not run (exit $code)" >&2; exit 2 ;;
esac
