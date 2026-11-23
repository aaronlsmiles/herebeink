# Redeploy

The viewer is a static page: `web/dist` plus `tools/deploy/vercel.json`, on Vercel, served at `herebeink.studionephele.com`. The scene (`scene.json`, the `.spz` files and `coastline.json`) is not part of it: it lives on the media host, and the page learns where from `VITE_SCENE_URL`, baked in at build. The ladder (Part 2) sits beside the scene at `<prefix>/ladder/ladder.json` unless `VITE_LADDER_URL` names another; since 23 Nov it does (`herebeink/v3/ladder-2/ladder.json`, the ladder with R2 placed under Amendment 3), because published objects never change and a changed ladder takes a new prefix.

Nothing here has been deployed. A production deploy is public, so it runs only on the owner's word.

```bash
GO_LIVE=yes tools/deploy/deploy-production.sh
```

It runs `tools/deploy/stage.sh` (build, stage `deploy/production/`, identifier scan on exactly what ships, staged size), links the folder to the Vercel project `herebeink` once, and deploys to production. It refuses without `GO_LIVE=yes`.

To stage and scan without deploying:

```bash
VITE_SCENE_URL=https://<media-host>/<prefix>/scene.json tools/deploy/stage.sh
```

What stays out of the staged folder: `fixture/`, `sample/`, `spike.html`, `smoke.html`, source maps and any splat file. The script refuses if one is there.

## One gitignored file

`.env.local` at this repo's root:

```
VERCEL_SCOPE=<the Vercel scope slug to deploy under>
VITE_SCENE_URL=https://<media-host>/<prefix>/scene.json
IDENTIFIER_SCAN=<path to a scanner script that checks the staged files for identifiers that must not ship>
DEPLOY_ENV_OP=<path to a 1Password env file>
```

`DEPLOY_ENV_OP` points at a file with one line, `VERCEL_TOKEN=` followed by a 1Password secret reference. Never a raw value, never `--token`. `stage.sh` refuses without `IDENTIFIER_SCAN` (or with a scanner that is missing), and `deploy-production.sh` refuses without `DEPLOY_ENV_OP` or its file.

## Media host

The page fetches the scene from another origin, so the media host must answer with CORS (`Access-Control-Allow-Origin` for `https://herebeink.studionephele.com` or `*`; `GET` and `HEAD`; the `Range` header if it is allowed). `pipeline/upload_media.py` and `MEDIA.md` own that side. The `.spz` files should be served as `application/octet-stream`.

## Cross-origin isolation

Not needed. Spark 2.4.0 does not use `SharedArrayBuffer` or `Atomics` (checked in its published bundle); its workers take transferred buffers. So `vercel.json` sets no `Cross-Origin-Opener-Policy` or `Cross-Origin-Embedder-Policy`, which would also have blocked the media host's responses unless it sent `Cross-Origin-Resource-Policy`. If a later Spark version needs them, add both headers and `Cross-Origin-Resource-Policy: cross-origin` on the media host together.

## Domain (once)

`vercel domains add herebeink.studionephele.com herebeink --scope "$VERCEL_SCOPE"`, then, in the DNS provider, a CNAME `herebeink` to `cname.vercel-dns.com`, DNS only (grey cloud), so Vercel issues the certificate.

A production deploy also gets Vercel's default `herebeink.vercel.app`. Share only `herebeink.studionephele.com`.

## Check, live

```bash
curl -sIL https://herebeink.studionephele.com                       # 200, Cache-Control max-age=0, must-revalidate
curl -sIL https://herebeink.studionephele.com/assets/<hashed>.js    # 200, immutable (take the name from the page source)
curl -sIL https://herebeink.studionephele.com/fonts/geist-latin.woff2   # 200
curl -sIL "$VITE_SCENE_URL"                                         # 200 and a CORS header from the media host
curl -sI -H "Origin: https://herebeink.studionephele.com" "$VITE_SCENE_URL" | grep -i access-control
```

Then open the page, wait for the room, and check the console is clean. Open `?hud=1` on the phone for the frame time.
