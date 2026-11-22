import { mkdtempSync, readFileSync, rmSync, existsSync } from "node:fs";
import { createServer, request, type Server } from "node:http";
import type { AddressInfo } from "node:net";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { afterAll, beforeAll, describe, expect, it } from "vitest";
import { frameHandler, framePath, MAX_FRAME_BYTES } from "./frame-dump.ts";

const root = resolve("/repo/film/frames");

describe("framePath", () => {
  it("pads the frame number and keeps to the folder", () => {
    expect(framePath(root, "7", null)).toBe(resolve(root, "00007.png"));
    expect(framePath(root, "12345", "take-2")).toBe(resolve(root, "take-2/12345.png"));
  });
  it("refuses anything that is not a plain frame number and set name", () => {
    for (const n of ["", "-1", "1.5", "1e3", "123456", "../1", "1/../../x", "00001.png", " 1"]) expect(framePath(root, n, null)).toBeNull();
    for (const set of ["..", "../x", "a/b", "A", "-x", "", "x".repeat(33), "a b", "a\\b"]) expect(framePath(root, "1", set)).toBeNull();
    expect(framePath(root, null, null)).toBeNull();
  });
});

describe("frameHandler", () => {
  let dir: string;
  let server: Server;
  let port: number;
  beforeAll(async () => {
    dir = mkdtempSync(join(tmpdir(), "frames-"));
    server = createServer(frameHandler(join(dir, "film/frames")));
    await new Promise<void>((r) => server.listen(0, "127.0.0.1", r));
    port = (server.address() as AddressInfo).port;
  });
  afterAll(() => { server.close(); rmSync(dir, { recursive: true, force: true }); });

  // A browser page on the dev server sends its own origin and the blob's type with every POST.
  const own = () => ({ Origin: `http://127.0.0.1:${port}`, "Content-Type": "image/png" });
  const send = (path: string, body: Buffer | string, method = "POST", headers: Record<string, string> = own()) => new Promise<{ status: number; text: string }>((ok, fail) => {
    const req = request({ host: "127.0.0.1", port, path, method, headers }, (res) => {
      let text = "";
      res.on("data", (c) => (text += c));
      res.on("end", () => ok({ status: res.statusCode ?? 0, text }));
    });
    req.on("error", fail);
    req.end(body);
  });

  it("writes the body to the numbered file, in a set when asked", async () => {
    const png = Buffer.from([0x89, 0x50, 0x4e, 0x47, 1, 2, 3]);
    expect((await send("/?n=3", png)).status).toBe(200);
    expect(readFileSync(join(dir, "film/frames/00003.png")).equals(png)).toBe(true);
    expect((await send("/?n=0&set=take-1", png)).status).toBe(200);
    expect(existsSync(join(dir, "film/frames/take-1/00000.png"))).toBe(true);
  });
  it("refuses a request from another origin, one with no origin, and one that is not a PNG, and writes nothing", async () => {
    const png = Buffer.from([0x89, 0x50, 0x4e, 0x47]);
    // A page on another site can post to the dev server's port from the visitor's own machine.
    expect((await send("/?n=20", png, "POST", { ...own(), Origin: "https://evil.example" })).status).toBe(403);
    expect((await send("/?n=20", png, "POST", { ...own(), Origin: `http://localhost:${port}` })).status).toBe(403);
    expect((await send("/?n=20", png, "POST", { "Content-Type": "image/png" })).status).toBe(403);
    expect((await send("/?n=21", png, "POST", { ...own(), "Content-Type": "text/plain" })).status).toBe(415);
    expect((await send("/?n=21", png, "POST", { Origin: own().Origin })).status).toBe(415);
    expect(existsSync(join(dir, "film/frames/00020.png"))).toBe(false);
    expect(existsSync(join(dir, "film/frames/00021.png"))).toBe(false);
  });
  it("refuses traversal, other methods and oversize bodies, and writes nothing for them", async () => {
    expect((await send("/?n=../../escape", "x")).status).toBe(400);
    expect((await send("/?n=1&set=..", "x")).status).toBe(400);
    expect((await send("/?n=1", "x", "GET")).status).toBe(405);
    expect(existsSync(join(dir, "escape.png"))).toBe(false);
    // The server may cut the connection while the client is still sending, which is a refusal too.
    const big = await send("/?n=9", Buffer.alloc(MAX_FRAME_BYTES + 1024)).catch(() => ({ status: 413, text: "reset" }));
    expect(big.status).toBe(413);
    expect(existsSync(join(dir, "film/frames/00009.png"))).toBe(false);
  }, 30_000);
});
