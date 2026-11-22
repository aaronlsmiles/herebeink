import { createWriteStream, mkdirSync, rmSync } from "node:fs";
import type { IncomingMessage, ServerResponse } from "node:http";
import { resolve, sep } from "node:path";
import type { Plugin } from "vite";

/** One 4K PNG of a drawn frame is well under this; anything bigger is not a frame. */
export const MAX_FRAME_BYTES = 64 * 1024 * 1024;

/**
 * Where frame `n` of `set` goes under `root`, or null if the request names anything but a plain
 * frame number and a plain set name. The path is built from validated parts and checked again.
 */
export function framePath(root: string, n: string | null, set: string | null): string | null {
  if (n === null || !/^\d{1,5}$/.test(n)) return null;
  if (set !== null && !/^[a-z0-9][a-z0-9-]{0,31}$/.test(set)) return null;
  const dir = resolve(root, set ?? ".");
  if (dir !== root && !dir.startsWith(root + sep)) return null;
  const file = resolve(dir, `${n.padStart(5, "0")}.png`);
  return file.startsWith(dir + sep) ? file : null;
}

const LOOPBACK = new Set(["127.0.0.1", "::1", "::ffff:127.0.0.1"]);

function reply(res: ServerResponse, status: number, text: string) {
  res.statusCode = status;
  res.setHeader("Content-Type", "text/plain; charset=utf-8");
  res.end(text);
}

/**
 * The loopback check alone lets any web page the developer has open post to this port from their
 * own machine, so the request must also come from a page this server served: a browser sends the
 * page's origin with every POST, and it has to be the host the request was made to.
 */
function sameOrigin(req: IncomingMessage): boolean {
  const origin = req.headers.origin;
  const host = req.headers.host;
  if (!origin || !host) return false;
  return origin === `http://${host}` || origin === `https://${host}`;
}

/** POST /frame?n=<frame>[&set=<name>] with a PNG body writes <root>/[<name>/]NNNNN.png. */
export function frameHandler(root: string) {
  return (req: IncomingMessage, res: ServerResponse) => {
    if (req.method !== "POST") return reply(res, 405, "POST only");
    if (!LOOPBACK.has(req.socket.remoteAddress ?? "")) return reply(res, 403, "local requests only");
    if (!sameOrigin(req)) return reply(res, 403, "frames come from the dev server's own page only");
    if (!/^image\/png\s*(;|$)/i.test(req.headers["content-type"] ?? "")) return reply(res, 415, "a frame is image/png");
    const url = new URL(req.url ?? "", "http://local");
    const file = framePath(root, url.searchParams.get("n"), url.searchParams.get("set"));
    if (!file) return reply(res, 400, "a frame needs ?n=<digits> and an optional plain ?set=<name>");
    const declared = Number(req.headers["content-length"] ?? 0);
    if (declared > MAX_FRAME_BYTES) return reply(res, 413, "frame too large");
    mkdirSync(resolve(file, ".."), { recursive: true });
    const out = createWriteStream(file);
    let size = 0;
    let refused = false;
    req.on("data", (chunk: Buffer) => {
      size += chunk.length;
      // The header can lie or be absent (chunked), so the cap is also counted as the body arrives.
      if (size > MAX_FRAME_BYTES && !refused) {
        refused = true;
        out.once("close", () => rmSync(file, { force: true }));
        out.destroy();
        reply(res, 413, "frame too large");
        req.destroy();
        return;
      }
      if (!refused) out.write(chunk);
    });
    req.on("end", () => {
      if (refused) return;
      out.end(() => reply(res, 200, "ok"));
    });
    req.on("error", () => out.destroy());
  };
}

/** Dev server only: the film page posts each drawn frame here, and ffmpeg reads them from film/frames/. */
export function frameDump(repoRoot: string): Plugin {
  return {
    name: "herebeink-frame-dump",
    apply: "serve",
    configureServer(server) {
      server.middlewares.use("/frame", frameHandler(resolve(repoRoot, "film/frames")));
    },
  };
}
