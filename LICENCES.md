# Licences and terms

What this project uses, under which terms, and what those terms ask of it. A reading of the terms, not legal advice. Read 18 Nov 2026.

## World Labs (Marble, through the World API)

### Terms in force

| Document | Date shown | Note |
|---|---|---|
| Terms of Service (Marble and World API), docs.worldlabs.ai/terms-of-service | Last updated 21 Jan 2026 | The version the World API docs link to |
| Terms of Service (rewrite, published with Atlas), docs.atlas.worldlabs.ai/terms-of-service.md | "11.10.26" | Covers all World Labs services; the date is written US-style, probably 10 Nov 2026 |
| Acceptable Use Policy, worldlabs.ai/aup | Last modified 12 Nov 2025 | Prevails over the TOS where they conflict |

Both TOS versions give paid API users the same output rights, so the reading does not depend on which is in force. Each world below is stamped with the terms version on the day it was generated.

### Who owns the output

- **TOS 21 Jan 2026, §3.3(b) "Paid Accounts and API":** paid account users "own all rights, title, and interest in and to Outputs generated through their use of the Services" and may "publish … create derivative works from, distribute, publicly perform and display … the Output for any purpose, including Commercial Purposes, provided that such use complies with this TOS."
- **TOS 21 Jan 2026, §3.3(d) "Other API Rights":** API users may use, modify, distribute and sublicense the Output for Commercial Purposes, subject to the TOS and any attribution requirements.
- **TOS 11.10.26, §2.3(b) "Eligible Paid Access":** "Customer owns Outputs generated through Eligible Paid Access", with the same rights to publish, display and make derivative works, "including Commercial Purposes".

This project treats its page as commercial use (a studio portfolio counts as "Marketing and Promotional Use"), which the API route allows. Only worlds generated through the paid World API appear here. Worlds made in the Marble web app on a Free or Standard plan are owned by World Labs and licensed for non-commercial use only; none is used.

The account holds a positive credit balance whenever a world is generated, so it is plainly a paid account at that moment (TOS 21 Jan 2026, §3.3(c): "Account status is determined at the time of Output generation").

### Attribution and provenance

- The origin and method of creation of the output are never misrepresented (TOS 21 Jan 2026 §3.7(b)(i); 11.10.26 §2.7).
- World Labs is credited in words (never the logo; TOS §3.4). The README and the thesis carry "Imagined world generated with World Labs Marble (marble-1.1-plus) through the World API; re-rendered in ink by Studio Nephele."; the film's end card "Imagined half generated with World Labs Marble (marble-1.1-plus) through the World API; drawn in ink by the page."; the page's first screen, from `scene.json`'s `credit`, "The imagined half was generated with Marble by World Labs, through its World API." Wherever a model is named, it is the world kept (marble-1.1-plus). No fixed wording is required by World Labs today; if they ask for one, it replaces these.
- Any watermark, notice or provenance data World Labs embeds in an output is kept, never removed or altered (TOS 21 Jan 2026 §3.7(d); 11.10.26 §2.7).

### AI disclosure

AUP §2.7: "Users must disclose when AI-generated content from the Services is used in communications, publications, or presentations where recipients could reasonably be expected to believe the content is human-created". The ink pass makes Marble's output look hand-drawn, so this applies directly. The page's first screen states the rule: the photograph is what the camera measured; the drawing is what the model made up beyond it. The ink half is never captioned as drawn by hand.

### No competitive benchmarking

TOS 21 Jan 2026 §2.8(d) bars using the Services to "engage in competitive analysis or benchmarking"; TOS 11.10.26 §1.10(d) bars "competitive benchmarking of the Services".

How this project words its residual: the alignment residual is the quality of the fit between one Marble world and one capture of this room. It is never presented as a Marble accuracy score, and never set beside another model's numbers. A note to World Labs asks whether Part 2's ladder (Marble compared with itself on this room) is fine under the clause before any of its numbers are published.

### Inputs and training opt-out

- Inputs and outputs may be used by World Labs for training unless the paid user opts out (TOS 21 Jan 2026 §3.6; 11.10.26 §2.6). The opt-out works going forward only.
- State: the training opt-out was switched on in the Marble app's settings on 18 Nov 2026 (hub call 28); the World Labs Platform has no separate toggle. Whether that switch covers API uploads has been asked of World Labs; answer pending.
- Every upload sends `permission: {public: false}` and goes up as a media asset, never by public URL. The pano still passes a privacy check before it is uploaded.

### Worlds generated

| Date | World id | Model | Credits | Terms version |
|---|---|---|---|---|
| 2026-11-20 | a11bacfe-0c0c-49f4-8fce-ca0a94ca6481 | marble-1.0-draft | 150.0 | TOS 21 Jan 2026; rewrite dated 11.10.26 noted |
| 2026-11-20 | 10361775-79cf-40d6-8193-a5dfa026f588 | marble-1.0-draft | 150.0 | TOS 21 Jan 2026; rewrite dated 11.10.26 noted |
| 2026-11-20 | 644d28e8-7f21-4cfc-baa4-f2098f0e753f | marble-1.1 | 1500.0 | TOS 21 Jan 2026; rewrite dated 11.10.26 noted |
| 2026-11-20 | 9f68512c-ac97-4fe4-87d2-b27d936620cc | marble-1.1-plus | 1500.0 | TOS 21 Jan 2026; rewrite dated 11.10.26 noted |
| 2026-11-22 | dff477c0-0d6e-4a2e-99e1-cfff3c1652df | marble-1.1-plus | 1580.0 | TOS 21 Jan 2026; rewrite dated 11.10.26 noted |
| 2026-11-22 | 2e423da6-ab61-4eb3-9550-e600b9b71545 | marble-1.1-plus | 1600.0 | TOS 21 Jan 2026; rewrite dated 11.10.26 noted |
| 2026-11-23 | 7bce8b02-f36e-4844-b2c8-203954aa039e | marble-1.1-plus | 1600.0 | TOS 21 Jan 2026; rewrite dated 11.10.26 noted |
| 2026-11-23 | 014662b9-66ee-4ca6-9c47-8bb3b2bf1416 | marble-1.1-plus | 1600.0 | TOS 21 Jan 2026; rewrite dated 11.10.26 noted |
| 2026-11-23 | c4bda756-c9b8-4636-8c37-cf27f25a1ba9 | marble-1.1-plus | 1600.0 | TOS 21 Jan 2026; rewrite dated 11.10.26 noted |
| 2026-11-23 | 762513d0-0387-4d9e-a38e-aba3a334e92d | marble-1.1-plus | 1600.0 | TOS 21 Jan 2026; rewrite dated 11.10.26 noted |

## Third-party software and fonts

| Component | Licence | Use here |
|---|---|---|
| LichtFeld Studio | GPL-3.0 | Trains the splat; run as a tool, none of its code is in this repo |
| Spark (`@sparkjsdev/spark`, World Labs) | MIT | The splat renderer in the viewer, bundled into the page; also writes the SPZ files |
| three.js | MIT | The viewer's 3D library, bundled into the page |
| SuperSplat | MIT | Cleans the splat; run as a tool |
| SPZ format (Niantic) | MIT | The splats' file format for the web (written with Spark's encoder) |
| Geist and Geist Mono | SIL Open Font License 1.1 | The page's typefaces, self-hosted; the licence is `web/public/fonts/OFL.txt` |
| COLMAP | BSD-3-Clause | Reconstructs camera poses; run as a tool |

## This repository

- **Code:** MIT ([LICENSE](LICENSE)).
- **The fixture world and its pictures** (`web/public/fixture/`, `docs/viewer/`): synthetic, made by `pipeline/make_fixture.py` and rendered by this viewer; no capture and no Marble output in them. Covered by the same licence as the code.
- **The spike screenshots** (`docs/spike-s1/`): renders of Spark's public sample splat (`butterfly.spz`, from sparkjs.dev, World Labs). Spark's docs and repository state no licence for the sample; the sample itself is not in this repository (`web/tools/fetch-sample.sh` downloads it).
- **Not in this repository:** the capture, the trained splat, the Marble world and the film. The splats and `scene.json` are served from the media host; the film has no audio track.
