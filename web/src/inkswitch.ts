/**
 * The ink/filter switch: the imagined half is drawn in ink, or shown as a plain
 * desaturate-and-contrast filter with no outlines, so every visitor can compare the two. It changes
 * the imagined half's shading only; the URL carries the state so a shared link keeps it.
 */
export class InkSwitch {
  readonly button: HTMLButtonElement;
  private on: boolean;

  constructor(initial: boolean, private readonly apply: (inkOn: boolean) => void) {
    this.on = initial;
    this.button = document.createElement("button");
    this.button.type = "button";
    this.button.className = "chip";
    this.button.dataset.control = "ink";
    this.button.addEventListener("click", () => this.set(!this.on));
    this.render();
  }

  get inkOn() {
    return this.on;
  }

  set(on: boolean) {
    if (on === this.on) return;
    this.on = on;
    this.render();
    this.apply(on);
    const url = new URL(location.href);
    if (on) url.searchParams.delete("ink");
    else url.searchParams.set("ink", "off");
    history.replaceState(history.state, "", url);
  }

  private render() {
    this.button.setAttribute("aria-pressed", String(!this.on));
    this.button.textContent = this.on ? "Imagined half: ink" : "Imagined half: filter";
    this.button.title = this.on ? "Show the imagined half as a plain filter instead" : "Draw the imagined half in ink again";
  }
}
