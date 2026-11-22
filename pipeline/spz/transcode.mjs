// PLY -> SPZ with Spark's own encoder, the same code (and version) that decodes the files in the viewer.
//   node spz/transcode.mjs jobs.json      jobs.json: [{"in": "a.ply", "out": "a.spz"}, ...]
// Files are written in their own frame: Spark 2.4.0's transcoder rotates positions but not spherical
// harmonics, so frames are changed by the viewer's mesh matrix instead (see splats.py).
import { readFileSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const SPARK_VERSION = "2.4.0";
const here = dirname(fileURLToPath(import.meta.url));
const sparkDir = resolve(here, "../../web/node_modules/@sparkjsdev/spark");
let pkg;
try {
  pkg = JSON.parse(readFileSync(resolve(sparkDir, "package.json"), "utf8"));
} catch {
  console.error(`Spark not found at web/node_modules: run 'npm ci' in web/ first`);
  process.exit(2);
}
if (pkg.version !== SPARK_VERSION) {
  console.error(`web/ has Spark ${pkg.version}; this encoder is pinned to ${SPARK_VERSION}, the viewer's version`);
  process.exit(2);
}
const { transcodeSpz } = await import(resolve(sparkDir, "dist/spark.module.js"));
const jobs = JSON.parse(readFileSync(process.argv[2], "utf8"));
for (const job of jobs) {
  const fileBytes = new Uint8Array(readFileSync(job.in));
  const { fileBytes: out } = await transcodeSpz({ inputs: [{ fileBytes, pathOrUrl: job.in }], maxSh: job.maxSh ?? 3 });
  writeFileSync(job.out, out);
  console.log(`${job.out}: ${out.length} bytes`);
}
