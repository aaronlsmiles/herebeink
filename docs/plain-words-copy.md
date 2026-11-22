# Plain words: the copy

The words for Here Be Ink's plain-words layer, written to the studio method (`docs/plain-words.md` in the studio hub). They tell the same story as the page and the thesis to a bright 12-year-old, or to anyone new to the field. The layer is additive: it never edits the page's own copy.

Each piece says where it goes. Set the words exactly as written; the checks (facts, jargon, reading level) run on this text.

## Notes for whoever wires it in

- **Hide the layer on the hallway link.** With `?coast=off`, hide the invite and the top-bar switch, and ignore `?plain=1`. Chapters 2 and 3 and the coastline note say where the line falls, which is the one thing the hallway walkers must find for themselves.
- **Film and headset.** Keep the layer off in film mode (`?path=film`). In a headset the page's own text is not shown, so neither is the layer.
- **Don't give the line away early.** Chapter 1 tells the reader to look for the edge, not where it is. Chapter titles are neutral for the same reason, since the story map shows them all.
- **Chapters follow the walk.** Each band opens on its own at its moment (below). "Next" opens the next band's words without moving the camera. Each moment fires once; after that, the reader moves with "Next" or the story map.
- **Labels in quotes** are the page's visible labels as of 22 November ("Walk in", "Map", "About", "Imagined half: ink", "Imagined half: filter", "Look by tilting the phone", "Enter VR", and the map legend's "Photograph", "Half and half", "Drawing", "Pen line" and "You"). If a label changes, change its quote here to match.
- **Numbers.** The layer uses no digits except the chapter count ("1 of 5"). Every number is in words and has a match in `THESIS.md`: three passes; one photo; more than a million (1.5 million splats trained); about a metre (1.1 m of hallway); about three in every hundred (2.9 %).

## The invite

**Where:** the first screen (`section.intro`), straight after the statement (`p.statement`), before "Walk in". The studio's shared words, unchanged:

> New to this? Read it in plain words

**Where:** every band carries the hide control, and the top bar (`nav.bar`) carries the switch that brings the layer back:

> Hide plain words

> Plain words

## Chapter bands

A band is a labelled region (`tabindex="-1"`) laid over the edge of the walk view, never its middle. Focus moves into it when it opens.

### In plain words · 1 of 5: Arriving

**When:** as soon as the layer is turned on, on the first screen below the statement. After "Walk in", it stays open over the walk until chapter 2's moment.

This is my room. It's real, and you can walk around in it.

I filmed it with a camera that sees all the way round at once. I carried it slowly round the room three times, each time at a different height. Then a computer worked out the room's shape from all those pictures.

So where it looks like a photo, the camera really saw it, from lots of places. That's what the page means by "measured".

Somewhere, the photo turns into a drawing. Walk around and see if you can find where.

Next: The edge →

### In plain words · 2 of 5: The edge

**When:** the first time the floor's pen line is on screen and the visitor stands within about two metres of it.

You found it. This door frame is where my measuring stops. Nothing past it was measured.

Here's where the rest came from. I gave one photo of my room to an AI program called Marble, made by a company called World Labs. From that one photo, it built a whole world you can walk through.

Most of its world landed right on top of my real room. There, the page shows my version. Only past the door does it show Marble's, and it draws that part in ink.

Next: Stepping over →

### In plain words · 3 of 5: Stepping over

**When:** the moment the visitor's position crosses the floor's pen line onto the drawn side.

Now you're standing in the guess. Marble made all of this up from one photo.

There is a real hallway out there. I filmed it too, but I kept that film back. Later I'll check the guess against it.

The page draws the guess as you move. Darker parts get more pen strokes, in rows. Edges get a pen outline that stays the same thickness, however close you get.

The made-up part is small: about a metre of hallway, and a hint of where it turns.

Next: Looking back →

### In plain words · 4 of 5: Looking back

**When:** on the drawn side, the first time the visitor turns to face the room (the floor's pen line in front of the camera again).

Turn round. The room is still a photo.

That's the whole idea. The look of each part tells you where it came from, wherever you stand. You don't need a label.

Here's why that matters. AI programs can now add to real places with no join you can see. A made-up hallway can look as real as the room it's stuck to. A label saying "made by AI" gets cut off a screenshot. A drawing style stays in every picture you take.

Next: The map →

### In plain words · 5 of 5: The map

**When:** the first time the map opens ("Map", or the M key).

This is the room from above, with the ceiling taken off so you can see the floor. The mark labelled "You" is where you're standing.

The part marked "Drawing" is small. It's about three in every hundred pieces of Marble's world.

The surprise was how hard the edge was to find. The camera's room is mostly fog. It's made of more than a million tiny blobs of colour, and nearly all of them are almost see-through. Stack enough of them and they look like a wall.

My first test counted the fog as solid wall. So it said Marble had made up almost nothing, and it found no edge at all. In the end I chose where the measuring stops: the door frame. Past it, the camera's room is only fog.

## Notes beside the coastline

**Where:** pinned in the walk view beside the floor's pen line while it is on screen and close. If a note can't be pinned in the scene, show it under chapter 2's band.

> This pen line is the edge of what the camera measured. On the room's side is what the camera measured. On the far side is what was made up.
>
> There's a second line too. The page draws it round the made-up part on your screen, wherever you stand.
>
> Old mapmakers sometimes drew sea monsters where their maps ran out. This page draws ink.

## Notes on the map

**Where:** inside the map's legend (`section.map-legend`), after its heading "The survey from above" and before the list.

> Each colour on this map says where that part came from.
>
> "Photograph" means the camera measured it. "Drawing" means Marble made it up, far from anything the camera saw. "Half and half" is Marble's too, but close to something measured, so the page draws it half and half. "Pen line" marks where the measured floor ends.

## Notes on the controls

Each note sits just before or beside the control it explains.

**"Walk in"** (the main button on the first screen):

> This puts you inside the room. Walk slowly and look around as you go.

**The loading line** (`p.status`, while it reads "Loading the room…"):

> The room arrives blurry first, then sharpens as the rest comes in. Phones get a lighter copy of the room, so they can keep up.

**"Imagined half: ink" / "Imagined half: filter"** (the switch in the top bar):

> This switch only changes the made-up part. "Imagined half: ink" draws it in pen. "Imagined half: filter" just takes the colour out, the way a photo app would.
>
> Flip it and compare. The question here is which one tells you more plainly that nobody measured it. You get to judge.

**"Map"** (top bar; the M key on a keyboard):

> This shows the room from above, like a map. Tap it again to go back to walking.

**"About"** (top bar):

> This brings back the first screen and the rule.

**"Look by tilting the phone"** (phones only):

> This lets you look round by moving your phone, like a window into the room. Your phone asks first. If it won't, drag with a finger instead.

**"Enter VR"** (only when a headset is ready):

> This only shows up when a headset can start. In a headset, the made-up part is plain paper, with the line on the floor. The pen strokes only work on a screen for now. I haven't tried it in a headset myself yet.

**The phone line** (`p.device`, on the first screen):

> I timed the page on my own iPhone. Android phones haven't been tested, so the page doesn't promise they'll work.

**The credit** (`p.credit`, on the first screen):

> World Labs made Marble, the AI program that built the made-up part. The ink is drawn by this page's own code, not by hand.
