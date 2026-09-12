import { afterEach, describe, expect, it, vi } from "vitest";
import { transitionScreen } from "./screenTransition";

afterEach(() => {
  Reflect.deleteProperty(document, "startViewTransition");
  delete document.documentElement.dataset.screenTransition;
  vi.restoreAllMocks();
});

describe("screen transitions", () => {
  it("updates immediately in older webviews", () => {
    const update = vi.fn();
    transitionScreen(update);
    expect(update).toHaveBeenCalledOnce();
  });
  it("respects reduced motion even when the browser supports transitions", () => {
    const start = vi.fn();
    Object.defineProperty(document, "startViewTransition", { configurable: true, value: start });
    vi.spyOn(window, "matchMedia").mockReturnValue({ matches: true } as MediaQueryList);
    const update = vi.fn();
    transitionScreen(update);
    expect(update).toHaveBeenCalledOnce();
    expect(start).not.toHaveBeenCalled();
  });
  it("captures an update with direction and cleans up after completion", async () => {
    vi.spyOn(window, "matchMedia").mockReturnValue({ matches: false } as MediaQueryList);
    let finish!: () => void;
    const finished = new Promise<void>((resolve) => { finish = resolve; });
    const start = vi.fn((update: () => void) => {
      update();
      return { finished, skipTransition: vi.fn() };
    });
    Object.defineProperty(document, "startViewTransition", { configurable: true, value: start });
    const menu = document.createElement("nav");
    menu.className = "bottom-action-navigation";
    document.body.append(menu);
    vi.spyOn(menu, "getClientRects").mockReturnValue([{}] as unknown as DOMRectList);
    const update = vi.fn();
    transitionScreen(update, "back");
    expect(update).toHaveBeenCalledOnce();
    expect(document.documentElement.dataset.screenTransition).toBe("back");
    expect(menu.style.viewTransitionName).toBe("app-navigation");
    finish();
    await finished;
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(document.documentElement.dataset.screenTransition).toBeUndefined();
    expect(menu.style.viewTransitionName).toBe("");
    menu.remove();
  });
});
