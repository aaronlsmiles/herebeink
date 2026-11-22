import { createReadStream, readFileSync, statSync } from "node:fs";
import type { IncomingMessage, ServerResponse } from "node:http";
import { resolve, sep } from "node:path";
import type { Plugin } from "vite";

const LOOPBACK = new Set(["127.0.0.1", "::1", "::ffff:127.0.0.1"]);
const FILE = /^[a-z0-9][a-z0-9-]{0,63}\.(json|spz)$/;

function reply(res: ServerResponse, status: number, text: string) {
  res.statusCode = status;
  res.setHeader("Content-Type", "text/plain; charset=utf-8");
  res.end(text);
}

/**
 * The export's scene.json with its filmPath taken from one shot of the film's path file
 * (`{ "shots": { "<name>": { "filmPath": [...] } } }`); nothing else changes.
 */
export function filmScene(exportDir: string, pathFile: string, shot: string): string {
  const scene = JSON.parse(readFileSync(resolve(exportDir, "scene.json"), "utf8")) as Record<string, unknown>;
  const film = JSON.parse(readFileSync(pathFile, "utf8")) as { shots?: Record<string, { filmPath?: unknown }> };
  const keys = film.shots?.[shot]?.filmPath;
  if (!Array.isArray(keys) || keys.length < 2) throw new Error(`${pathFile}: shot "${shot}" needs a filmPath of two keys or more`);
  return JSON.stringify({ ...scene, filmPath: keys });
}

/**
 * GET /film-scene/<file> serves <exportDir>/<file>; scene.json?shot=<name> is served with that
 * shot's path in place of the export's. Same origin as the page, so the splats need no CORS and never pass
 * through public/ (and so never reach a build).
 */
export function filmSceneHandler(exportDir: string, pathFile: string) {
  const dir = resolve(exportDir);
  return (req: IncomingMessage, res: ServerResponse) => {
    if (req.method !== "GET" && req.method !== "HEAD") return reply(res, 405, "GET only");
    if (!LOOPBACK.has(req.socket.remoteAddress ?? "")) return reply(res, 403, "local requests only");
    const url = new URL(req.url ?? "", "http://local");
    const name = decodeURIComponent(url.pathname.replace(/^\//, ""));
    if (!FILE.test(name)) return reply(res, 404, "not a scene file");
    const file = resolve(dir, name);
    if (!file.startsWith(dir + sep)) return reply(res, 404, "not a scene file");
    try {
      if (name === "scene.json") {
        const body = filmScene(dir, pathFile, url.searchParams.get("shot") ?? "walk");
        res.setHeader("Content-Type", "application/json");
        res.setHeader("Cache-Control", "no-store");
        res.end(req.method === "HEAD" ? undefined : body);
        return;
      }
      const size = statSync(file).size;
      res.setHeader("Content-Type", name.endsWith(".json") ? "application/json" : "application/octet-stream");
      res.setHeader("Content-Length", String(size));
      if (req.method === "HEAD") return res.end();
      createReadStream(file).pipe(res);
    } catch (e) {
      reply(res, 404, (e as Error).message);
    }
  };
}

/**
 * Dev server only, and only when HBI_FILM_EXPORT names a local export folder (relative to the repo):
 * the film renders from a local copy so its camera path can be corrected without touching the
 * published media, which are immutable.
 */
export function filmSceneServer(repoRoot: string): Plugin {
  return {
    name: "herebeink-film-scene",
    apply: "serve",
    // A dump runs for minutes; an edit to the page from another session must not reload it mid-shot.
    config: () => (process.env.HBI_FILM_EXPORT ? { server: { hmr: false } } : {}),
    configureServer(server) {
      const exportDir = process.env.HBI_FILM_EXPORT;
      if (!exportDir) return;
      const pathFile = process.env.HBI_FILM_PATH ?? resolve(repoRoot, "film/paths.json");
      server.middlewares.use("/film-scene", filmSceneHandler(resolve(repoRoot, exportDir), pathFile));
    },
  };
}
