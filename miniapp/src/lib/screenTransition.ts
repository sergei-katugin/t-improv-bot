import { flushSync } from "react-dom";

type Direction = "forward" | "back" | "tab-forward" | "tab-back" | "sheet";
type Transition = { finished: Promise<void>; skipTransition: () => void };
type TransitionDocument = Document & { startViewTransition?: (update: () => void) => Transition };
let running: Transition | undefined;

function nameNavigation() {
  const menus = [...document.querySelectorAll<HTMLElement>(".bottom-action-navigation")];
  menus.forEach((menu) => { menu.style.viewTransitionName = "none"; });
  const visible = menus.filter((menu) => menu.getClientRects().length > 0);
  const menu = visible[visible.length - 1];
  if (menu) menu.style.viewTransitionName = "app-navigation";
}

export function transitionScreen(update: () => void, direction: Direction = "forward") {
  const doc = document as TransitionDocument;
  if (!doc.startViewTransition || window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
    update();
    if (!window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      document.querySelectorAll<HTMLElement>(".show-detail, .show-list, .mantine-Modal-body").forEach((content) => {
        content.animate?.([{ opacity: 0 }, { opacity: 1 }], { duration: 200, easing: "ease-out" });
      });
    }
    return;
  }
  running?.skipTransition();
  document.documentElement.dataset.screenTransition = direction;
  nameNavigation();
  const transition = doc.startViewTransition(() => {
    flushSync(update);
    nameNavigation();
  });
  running = transition;
  void transition.finished.catch(() => undefined).finally(() => {
    if (running !== transition) return;
    running = undefined;
    delete document.documentElement.dataset.screenTransition;
    document.querySelectorAll<HTMLElement>(".bottom-action-navigation").forEach((menu) => {
      menu.style.removeProperty("view-transition-name");
    });
  });
}
