// Drives work/door/pick.html in headless Chromium the way a person would, and prints what it produced.
//   node tests/door_page_check.mjs PAGE.html
// Opened from a file, so no server and no socket beyond the browser's own pipe.
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const { chromium } = await import(join(resolve(here, "../../web/node_modules"), "playwright/index.mjs"));
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
const errors = [];
page.on("pageerror", (e) => errors.push(e.message));
page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
const loaded = () => page.waitForFunction(() => { const im = document.getElementById("im"); return im.complete && im.naturalWidth > 0; });
try {
  await page.goto("file://" + resolve(process.argv[2]));
  await loaded();
  const first = await page.evaluate(() => document.getElementById("cur").textContent);
  let box = await page.locator("#im").boundingBox();
  await page.mouse.move(box.x + 100, box.y + 200);
  const hover = await page.textContent("#coords");
  await page.mouse.click(box.x + 100, box.y + 200);                       // A in the first view
  await page.getByRole("button", { name: /^B / }).click();
  await page.mouse.click(box.x + 300, box.y + 210);                       // B in the first view
  await page.locator("#views button").nth(1).click();                      // the second view
  await loaded();
  const second = await page.evaluate(() => document.getElementById("cur").textContent);
  await page.evaluate(() => { document.getElementById("v").scrollTop = 400; });
  box = await page.locator("#im").boundingBox();
  await page.mouse.click(box.x + 310, box.y + 640);                       // B in the second view, scrolled
  await page.getByRole("button", { name: /^A / }).click();
  await page.mouse.click(box.x + 120, box.y + 600);                       // A in the second view
  const marks = await page.locator("#marks circle").count();
  const moreHidden = await page.evaluate(() => document.getElementById("moreviews").hidden);
  await page.locator("#more").click();
  const moreShown = await page.evaluate(() => !document.getElementById("moreviews").hidden);
  await page.locator("#moreviews button").first().click();
  await loaded();
  const third = await page.evaluate(() => document.getElementById("cur").textContent);
  const out = await page.inputValue("#out");
  const nFirst = await page.locator("#views button").count();
  const nMore = await page.locator("#moreviews button").count();
  console.log(JSON.stringify({ first, second, third, hover, out, marks, moreHidden, moreShown, nFirst, nMore, errors }));
} finally {
  await browser.close();
}
