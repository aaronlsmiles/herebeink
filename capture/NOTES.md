# Capture notes

Filled in on capture day. The media in this folder stay local (gitignored); this file is committed, so write nothing identifying here.

## Session

- Date: 19–20 Nov 2026 (one sitting, through midnight)
- Time (start, end): 23:08 (first still) to 01:23 (last phone still); passes 00:53–01:09
- Light: curtains (open / closed): closed
- Light: lamps (which, on / off): the room's ceiling light on; the hallway light on; the globe lamp on the shelf looks unlit in the stills
- Light: anything else (daylight at a fixed hour, etc.): night, no daylight. The hallway light is much warmer than the room's, so the hallway reads orange on every clip

## Camera (Insta360 X3)

- Mode and resolution: 360 Video, 5.7K (exports 5760 × 2880, H.265, Original bitrate); stills 360 Photo 72 MP and HDR
- Frame rate: 29.97 fps
- Exposure / ISO / white balance: video and the Manual still 1/100 s, ISO 640 (manual); white balance 4500K (manual)
- FlowState / stabilisation: off at export (the operator holds the 180° seam in every frame, which fits a frame fixed to the camera); Direction Lock off
- Other settings: stills exported as panoramic photo with automatic horizon levelling on; plain exports, not PureShot

## Passes

The room is narrow with a high ceiling: the loop runs as close to the middle as the room allows, not 0.6 m off every wall, and a pass takes about 1:40 at the slow pace. Two raised takes were deleted on 20 Nov: `_022` (walked too fast) and `_023` (screens on).

Read from contact sheets (20 Nov): the operator sits at the 180° seam in every frame of all three passes, so the frame is fixed to the camera. In the hip pass the body fills roughly yaw 95°–265°, wider than the default drops (180@0, 135@40, 225@40): check `cut_views.py preview` and drop 90@0 and 270@0 for hip if the body shows there. In the raised pass the head and shoulders reach about 45° below the horizon at the seam: check whether 180@0 needs dropping for raised too. Checked 20 Nov at `cut_views.py preview`: hip drops 90@0 and 270@0 as well (arm and body), raised drops 180@0 (top of the head); head as planned. The key pass turns the camera round on the way back, so the operator sits in different views over time; it is left as it is (COLMAP only, never trained on).

| Pass | Lens height | Filename | Duration |
|---|---|---|---|
| Head | 1.6 m | `_025` → pass-head.mp4 | 1:23 |
| Raised | as high as comfortable (high ceiling) | `_024` → pass-raised.mp4 | 1:20 |
| Hip | 0.9 m | `_026` → pass-hip.mp4 | 1:24 |
| Answer-key | 1.6 m | `_027` → pass-key.mp4 | 0:39 |

## Pano still

- Filenames taken, all from the same stand position (`pano.jpg` manual exposure, cut into views for COLMAP; `pano-auto.jpg` auto exposure, likely the one sent to Marble; `pano-hdr.jpg`): `pano.jpg` = `_014`, `pano-auto.jpg` = `_015`, `pano-hdr.jpg` = `_016–018` (plain exports, not PureShot). The first set (`_005–013`), the second HDR (`_019–021`) and the PureShot copies were deleted on 20 Nov; the raw files for `_014–021` stay in `raw/x3/`.
- First set, 19 Nov 23:08–23:13, read from the exports (shutter, ISO): `_005` Auto 18 MP (1/25, ISO 159); `_006` Auto 72 MP (1/25, ISO 158); `_007` Manual 72 MP (1/100, ISO 1600: about 1.3 stops brighter than Auto, 0.3 % of pixels clipped); `_008–010` and `_011–013` HDR brackets (18 MP, exported at 72 MP size). No person in frame. The two desk monitors were on (text not legible at full size), so the set is to be re-shot with screens off and the Manual ISO matched to Auto (about 640) before the passes.
- Second set (use this one), 19 Nov 23:59 – 20 Nov 00:01, read from the camera files: `_014` Manual 72 MP (1/100, ISO 640); `_015` Auto 72 MP (1/25, ISO 163); `_016–018` and `_019–021` HDR brackets (18 MP, 1/25, ISO 160). Screens off. No person in frame (the dark shape past the door edge is in the same place in every still from 23:09 to 00:01, so it hangs there). Passes: shutter 1/100, ISO 640.
- Stand height:
- Taken from (light stand / tripod), trigger (timer / app), operator out of the room (yes / no):

## Phone stills

- Count:
- Filenames (range):

## Scale anchor

- **Door frame inside width (tape), in metres:** 0.72 (A to B, at the floor, between the clicked points; re-taped 21 Nov: the first reading, 0.71 m, was taken to the middle of the jambs)
- Door frame inside width, second tape (cross-check), in metres: 0.715 (E to F, at the top of the frame, between the clicked points)
- Check length (what it is, and its length in metres): door frame inside height, C to D along the clicked edge (re-taped 21 Nov; the first reading was 1.94), 1.96

## Moved out or covered before the shoot

- Branded gear: storage-box labels and the desk audio unit's name taped over (green tape; two letters each side of the unit's tape still show). Laptop lid mark and sticker left as they were, masked in the stills
- Mirrors: none seen in any frame
- Screens: off for every X3 still and pass (the first still set and a raised take with screens on were deleted). On (lock screen) in 15 of the first phone stills; those 15 moved to `raw/phone-excluded/` and the desk re-shot with the screens off (IMG_4405–4423)
- Anything else: hallway doors closed, front door shut; nobody else about

## Phone for the measurement

- iPhone model: iPhone 15 Pro, main camera (6.765 mm, f/1.78); 62 stills used (IMG_4345–4423 less 15 excluded), 01:18 onwards
- iOS version: 27.3 (from the photos' metadata)

## Later (filled in at cleaning and scaling)

- Cleaning box: -2.21 1.87 -0.05 3.34 -1.47 1.85
  (x max moved from 3.83 to the door frame on 21 Nov, Aaron, call 62: the trained passes stayed in the room, and past the frame is fog seen through the doorway)
- Door points picked in the splat (two 3D points):

- Door click A rig/y000p00/3hip_0028.jpg: 254.1 1277.1
- Door click A rig/y000p00/5pano_0000.jpg: 421.8 1358.1
- Door click A rig/y270p00/2head_0017.jpg: 494.2 1262.8
- Door click B rig/y000p00/3hip_0028.jpg: 627.0 1279.1
- Door click B rig/y000p00/5pano_0000.jpg: 736.1 1336.6
- Door click B rig/y270p00/2head_0017.jpg: 714.5 1280.2
- Door click C rig/y000p00/3hip_0028.jpg: 254.1 1276.9
- Door click C rig/y000p00/5pano_0000.jpg: 421.8 1357.9
- Door click C rig/y270p00/2head_0017.jpg: 494.2 1262.8
- Door click D rig/y000p00/3hip_0028.jpg: 263.1 277.3
- Door click D rig/y000p00/5pano_0000.jpg: 430.8 510.9
- Door click D rig/y270p00/2head_0017.jpg: 531.6 648.3
- Door click E rig/y000p00/3hip_0028.jpg: 263.1 277.3
- Door click E rig/y000p00/5pano_0000.jpg: 430.8 510.6
- Door click E rig/y270p00/2head_0017.jpg: 531.6 648.3
- Door click F rig/y000p00/3hip_0028.jpg: 629.3 276.9
- Door click F rig/y000p00/5pano_0000.jpg: 729.9 514.1
- Door click F rig/y270p00/2head_0017.jpg: 746.6 655.5

## Privacy pass

Filled in by Task 1.3. No World Labs call may run until the last line of this file reads exactly `Clean for upload: yes` (any case, nothing else on the line).

- Checked (stitched passes, pano still, phone stills): all 23 sheets, 20 Nov (controller read, then Aaron's calls)
- Found: only the operator (Aaron) as a person, in the dropped views of the passes. Stills: laptop lid maker's mark and hex sticker; the desk audio unit's name partly showing round the tape; a third-party art print by the shelf (no person in it; Aaron: leave it). Hallway: front door (inside), coats, fuse box, intercom: nothing identifying (Aaron). Phone stills: the main monitor lit on the lock screen in 15 of them (excluded, re-shot with screens off); brand marks on the monitor, speakers, chair and alarm
- Masked (frames, areas): pano, pano-auto and pano-hdr: boxes 8510,4225,90,65 (laptop mark), 8770,4135,250,145 (sticker), 40,3900,340,100 (unit name). Passes left unmasked (Aaron: the marks blur away at the trained model's resolution)
- Confirmed by: Aaron, 20 Nov: masks 1 and 2 yes, the print stays, passes as they are, front door clear. Lit-screen phone stills excluded and re-shot. Aaron: "clean", 20 Nov

Clean for upload: yes
