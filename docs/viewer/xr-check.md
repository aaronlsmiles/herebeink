# Headset check (Quest 2 over Link, desktop Chrome)

Needs: Quest 2 with Link or Air Link running, desktop Chrome, `cd web && npm run dev` (localhost counts as a secure context; any other address needs HTTPS).

1. Open `http://localhost:5173/?hud=1`. Check that the **Enter VR** chip appears in the top bar (if it does not, `navigator.xr` is not offering `immersive-vr`: note that and stop). Open **About** and read the headset line ("outlines are drawn on screens, not yet in the headset").
2. Click **Enter VR** and put the headset on. Record whether the room is the right way up, at your real height, with the floor under your feet, and whether text or the pen line on the floor is visible.
3. Walk with the **left stick**: forward goes where your head points, not where the controller points. Turn your head while pushing; the direction should follow. Try to leave the room by walking out of the walkable area: you should slide along the edge and stop at the doorway's neck. Note any snag.
4. Turn with the **right stick**: each flick is 30 degrees, once per flick, with no drift while the stick rests. Check that the view turns about you, not about the room's origin.
5. Look at the picture per eye: close one eye then the other. Record any difference between eyes, shimmer, or splats popping when you turn your head (Spark sorts after rendering in a headset, so a little lag is expected).
6. Look through the doorway at the imagined hallway: it should be flat paper with no outlines or hatching (by design tonight), and the **floor coastline** (the pen line where the measured floor ends) should still be there.
7. Read the frame rate: in the headset use the Oculus performance overlay if you have it, or take off the headset after 30 s and read the HUD on the desktop window (`medianFrameMs`, `splatsRendered`, deviceClass should say `xr`, lod budget 500000).
8. Click **Exit VR** (or take the headset off). The desktop page must return to full size, the ink pass back, deviceClass `desktop`.

Record, in `LOG.md`: headset and browser versions, whether each of steps 2 to 8 held, the HUD numbers, and anything that looked wrong with a screenshot of the desktop window. If entering fails, copy the console warning "The headset session did not start".
