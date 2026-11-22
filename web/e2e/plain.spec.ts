// The plain-words trail on the fixture world: the invite, ?plain=1, the chapters opening at their moments of the
// walk, the notes, hiding and bringing it back, and the hallway link, where none of it exists.
import { expect, type Page, test } from "@playwright/test";
import { watchErrors } from "./helpers.ts";

async function open(page: Page, qs: string) {
  await page.goto(`/?${qs}`);
  await page.waitForSelector("html[data-ready='1']", { timeout: 180_000 });
}

/** The fixture's line runs across x ≈ 2.5 with the door's outward direction +x; the start stands at the origin facing it. */
async function stand(page: Page, x: number, z: number, yawDeg: number) {
  await page.evaluate(([px, pz, yaw]) => (window as any).__hbi.setPose(px, 1.6, pz, yaw, 0), [x, z, yawDeg]);
}

const band = (page: Page) => page.locator("#plain-words");

test("the invite offers the layer; taking it opens chapter 1 beside the statement, with the first screen's notes", async ({ page }) => {
  const errors = watchErrors(page);
  await open(page, "");
  const invite = page.locator(".intro .pw-invite");
  await expect(invite).toBeVisible();
  await expect(invite).toContainText("Read it in plain words");
  await expect(band(page)).toBeHidden();
  await expect(page.locator(".pw-note:visible")).toHaveCount(0);

  await invite.getByRole("button").click();
  await expect(band(page)).toBeVisible();
  await expect(band(page)).toHaveAttribute("data-chapter", "1");
  await expect(band(page)).toContainText("In plain words · 1 of 5");
  await expect(band(page)).toBeFocused();
  await expect(invite).toBeHidden();
  // The band sits in the invite's place, straight after the statement.
  expect(await page.evaluate(() => document.querySelector(".intro .statement")!.nextElementSibling!.nextElementSibling!.id)).toBe("plain-words");
  for (const id of ["walkIn", "credit", "device"]) await expect(page.locator(`.intro [data-note='${id}']`)).toBeVisible();
  expect(await page.evaluate(() => localStorage.getItem("herebeink-plain"))).toBe("on");
  // The page's own words are untouched.
  await expect(page.locator(".intro .credit")).toHaveText("The imagined half was generated with Marble by World Labs, through its World API.");
  expect(errors).toEqual([]);
});

test("?plain=1: the chapters open at their moments of the walk, then the map's, and hiding hands back to the switch", async ({ page }) => {
  const errors = watchErrors(page);
  await open(page, "plain=1");
  await expect(band(page)).toHaveAttribute("data-chapter", "1");
  await page.evaluate(() => (window as any).__hbi.chrome.hideIntro());
  await expect(page.locator(".pw-stack #plain-words")).toBeVisible();
  await expect(page.locator(".bar .pw-switch")).toHaveAttribute("aria-pressed", "true");

  await stand(page, 1.2, 0.05, -90);
  await expect(band(page)).toHaveAttribute("data-chapter", "2");
  await expect(band(page).locator("[data-note='coastline']")).toBeVisible();
  await stand(page, 2.8, 0.05, -90);
  await expect(band(page)).toHaveAttribute("data-chapter", "3");
  await expect(band(page).locator("[data-note='coastline']")).toBeHidden();
  await page.waitForTimeout(400);
  await stand(page, 2.8, 0.05, 90);
  await expect(band(page)).toHaveAttribute("data-chapter", "4");

  await page.keyboard.press("m");
  await expect(band(page)).toHaveAttribute("data-chapter", "5");
  await expect(page.locator(".map-legend [data-note='map']")).toBeVisible();
  await expect(band(page).locator(".pw-next")).toBeHidden();
  await page.keyboard.press("m");

  // Next moves on without moving the camera.
  await band(page).locator(".pw-trail button", { hasText: "Arriving" }).click();
  const pose = await page.evaluate(() => (window as any).__hbi.viewer.walk.pose().position.x);
  await band(page).locator(".pw-next").click();
  await expect(band(page)).toHaveAttribute("data-chapter", "2");
  expect(await page.evaluate(() => (window as any).__hbi.viewer.walk.pose().position.x)).toBe(pose);

  await band(page).getByRole("button", { name: "Hide plain words" }).click();
  await expect(band(page)).toBeHidden();
  await expect(page.locator(".bar .pw-switch")).toBeFocused();
  await expect(page.locator(".bar .pw-switch")).toHaveAttribute("aria-pressed", "false");
  expect(new URL(page.url()).searchParams.has("plain")).toBe(false);
  await page.reload();
  await page.waitForSelector("html[data-ready='1']", { timeout: 180_000 });
  await expect(band(page)).toBeHidden();
  await expect(page.locator(".intro .pw-invite")).toBeHidden();
  expect(errors).toEqual([]);
});

test("the hallway link (?coast=off) has no layer, no invite and no switch, even with ?plain=1", async ({ page }) => {
  const errors = watchErrors(page);
  await open(page, "coast=off&plain=1");
  await expect(page.locator(".intro .pw-invite")).toBeHidden();
  await expect(page.locator("#plain-words, .pw-switch, .pw-note, .pw-stack")).toHaveCount(0);
  await expect(page.locator(".intro .finding")).toHaveCount(0);
  expect(await page.evaluate(() => localStorage.getItem("herebeink-plain"))).toBeNull();
  expect(errors).toEqual([]);
});

test("About states the design pass's finding beside the ink, with the switch to compare", async ({ page }) => {
  await open(page, "");
  await expect(page.locator(".intro .finding")).toContainText("Here the ink reads as a filter, not a drawing.");
  await expect(page.locator(".intro .finding")).toContainText("“Imagined half”");
});
