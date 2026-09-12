import { flushSync } from "react-dom";

type Direction = "forward" | "back" | "tab-forward" | "tab-back" | "sheet";
type Transition = { finished: Promise<void>; skipTransition: () => void };
type TransitionDocument = Document & { startViewTransition?: (update: () => void) => Transition };
let running: Transition | undefined;

function nameNavigation() {
  const menus = [...document.querySelectorAll<HTMLElement>(".bottom-action-navigation")];
  menus.forEach((menu) => { menu.style.viewTransitionName = "none"; });
  document.querySelectorAll<HTMLElement>(".bottom-nav-selection").forEach((selection) => { selection.style.viewTransitionName = "none"; });
  const visible = menus.filter((menu) => menu.getClientRects().length > 0);
  const menu = visible[visible.length - 1];
  if (menu) {
    menu.style.viewTransitionName = "app-navigation";
    const selection = menu.querySelector<HTMLElement>(".bottom-nav-selection");
    if (selection) selection.style.viewTransitionName = "app-nav-selection";
  }
}

export function transitionScreen(update: () => void, direction: Direction = "forward") {
  const doc = document as TransitionDocument;
  if (!doc.startViewTransition || window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
    const previous = [...document.querySelectorAll<HTMLElement>(".bottom-nav-selection")].filter((node) => node.getClientRects().length).pop()?.getBoundingClientRect();
    flushSync(update);
    if (!window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      const contents = [...document.querySelectorAll<HTMLElement>("main.shell, .mantine-Modal-content")].filter((node) => node.getClientRects().length);
      const content = contents[contents.length - 1];
      const offset = direction === "back" || direction === "tab-back" ? "-12px" : "12px";
      content?.animate?.([{ translate: direction === "sheet" ? "0 16px" : `${offset} 0` }, { translate: "0 0" }], { duration: 220, easing: "ease-out" });
      const selection = [...document.querySelectorAll<HTMLElement>(".bottom-nav-selection")].filter((node) => node.getClientRects().length).pop();
      if (previous && selection) {
        const delta = previous.left - selection.getBoundingClientRect().left;
        const transform = getComputedStyle(selection).transform;
        selection.animate?.([{ transform: `translateX(${delta}px) ${transform === "none" ? "" : transform}` }, { transform }], { duration: 280, easing: "cubic-bezier(.22,1,.36,1)" });
      }
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
    document.querySelectorAll<HTMLElement>(".bottom-action-navigation, .bottom-nav-selection").forEach((menu) => {
      menu.style.removeProperty("view-transition-name");
    });
  });
}
