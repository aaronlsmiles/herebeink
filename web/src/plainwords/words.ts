// "In plain words": the walk's story for a bright 12-year-old, or for anyone new to the field, set exactly as
// docs/plain-words-copy.md has it. Additive: it never edits the page's own copy. The method is the studio's
// plain-words note; words.test.ts holds its rules (sourced numbers, field words only in quotes, the reading
// level, quoted labels that match the live controls).

export interface Chapter {
  /** Neutral on purpose: the story map shows every title, so none may say where the line falls. */
  title: string;
  text: string[];
}

export const CHAPTERS: Chapter[] = [
  {
    title: "Arriving",
    text: [
      "This is my room. It's real, and you can walk around in it.",
      "I filmed it with a camera that sees all the way round at once. I carried it slowly round the room three times, each time at a different height. Then a computer worked out the room's shape from all those pictures.",
      "So where it looks like a photo, the camera really saw it, from lots of places. That's what the page means by \"measured\".",
      "Somewhere, the photo turns into a drawing. Walk around and see if you can find where.",
    ],
  },
  {
    title: "The edge",
    text: [
      "You found it. This door frame is where my measuring stops. Nothing past it was measured.",
      "Here's where the rest came from. I gave one photo of my room to an AI program called Marble, made by a company called World Labs. From that one photo, it built a whole world you can walk through.",
      "Most of its world landed right on top of my real room. There, the page shows my version. Only past the door does it show Marble's, and it draws that part in ink.",
    ],
  },
  {
    title: "Stepping over",
    text: [
      "Now you're standing in the guess. Marble made all of this up from one photo.",
      "There is a real hallway out there. I filmed it too, but I kept that film back. Later I'll check the guess against it.",
      "The page draws the guess as you move. Darker parts get more pen strokes, in rows. Edges get a pen outline that stays the same thickness, however close you get.",
      "The made-up part is small: about a metre of hallway, and a hint of where it turns.",
    ],
  },
  {
    title: "Looking back",
    text: [
      "Turn round. The room is still a photo.",
      "That's the whole idea. The look of each part tells you where it came from, wherever you stand. You don't need a label.",
      "Here's why that matters. AI programs can now add to real places with no join you can see. A made-up hallway can look as real as the room it's stuck to. A label saying \"made by AI\" gets cut off a screenshot. A drawing style stays in every picture you take.",
    ],
  },
  {
    title: "The map",
    text: [
      "This is the room from above, with the ceiling taken off so you can see the floor. The mark labelled \"You\" is where you're standing.",
      "The part marked \"Drawing\" is small. It's about three in every hundred pieces of Marble's world.",
      "The surprise was how hard the edge was to find. The camera's room is mostly fog. It's made of more than a million tiny blobs of colour, and nearly all of them are almost see-through. Stack enough of them and they look like a wall.",
      "My first test counted the fog as solid wall. So it said Marble had made up almost nothing, and it found no edge at all. In the end I chose where the measuring stops: the door frame. Past it, the camera's room is only fog.",
    ],
  },
];

/** Notes beside the parts that confuse, by where each one sits. */
export const NOTES = {
  /** Beside the floor's pen line; shown under chapter 2's band, since a note pinned in the scene would move with every step. */
  coastline: [
    "This pen line is the edge of what the camera measured. On the room's side is what the camera measured. On the far side is what was made up.",
    "There's a second line too. The page draws it round the made-up part on your screen, wherever you stand.",
    "Old mapmakers sometimes drew sea monsters where their maps ran out. This page draws ink.",
  ],
  map: [
    "Each colour on this map says where that part came from.",
    "\"Photograph\" means the camera measured it. \"Drawing\" means Marble made it up, far from anything the camera saw. \"Half and half\" is Marble's too, but close to something measured, so the page draws it half and half. \"Pen line\" marks where the measured floor ends.",
  ],
  walkIn: ["This puts you inside the room. Walk slowly and look around as you go."],
  loading: ["The room arrives blurry first, then sharpens as the rest comes in. Phones get a lighter copy of the room, so they can keep up."],
  ink: [
    "This switch only changes the made-up part. \"Imagined half: ink\" draws it in pen. \"Imagined half: filter\" just takes the colour out, the way a photo app would.",
    "Flip it and compare. The question here is which one tells you more plainly that nobody measured it. You get to judge.",
  ],
  mapButton: ["This shows the room from above, like a map. Tap it again to go back to walking."],
  about: ["This brings back the first screen and the rule."],
  tilt: ["This lets you look round by moving your phone, like a window into the room. Your phone asks first. If it won't, drag with a finger instead."],
  vr: ["This only shows up when a headset can start. In a headset, the made-up part is plain paper, with the line on the floor. The pen strokes only work on a screen for now. I haven't tried it in a headset myself yet."],
  device: ["I timed the page on my own iPhone. Android phones haven't been tested, so the page doesn't promise they'll work."],
  credit: ["World Labs made Marble, the AI program that built the made-up part. The ink is drawn by this page's own code, not by hand."],
} satisfies Record<string, string[]>;

export type NoteId = keyof typeof NOTES;

/** The studio's shared wording on the controls, the same on every studio site. */
export const UI = {
  label: "In plain words",
  invite: "New to this?",
  follow: "Read it in plain words",
  hide: "Hide plain words",
  toggle: "Plain words",
  next: "Next:",
  chapters: "The story so far",
  /** The fold that holds the top bar's notes, closed on small screens so the room stays in view. */
  barNotes: "What these buttons do",
};

/** "In plain words · 2 of 5": the only digits the layer shows. */
export function chapterLabel(index: number) {
  return `${UI.label} · ${index + 1} of ${CHAPTERS.length}`;
}
