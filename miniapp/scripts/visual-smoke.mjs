import { mkdir } from "node:fs/promises";
import { resolve } from "node:path";
import { compareBaseline } from "./screenshot-baseline.mjs";
const { chromium } = await import(process.env.PLAYWRIGHT_MODULE_PATH || "playwright");
const output = resolve(process.env.VISUAL_OUTPUT || "visual-results");
await mkdir(output, { recursive: true });
const browser = await chromium.launch({ headless: true, ...(process.env.VISUAL_BROWSER_CHANNEL ? { channel: process.env.VISUAL_BROWSER_CHANNEL } : {}) });
const show = { id: 1, title: "Очень длинное название импровизационного шоу для проверки переноса", teamName: "Экспериментаторы", city: "Лимасол", location: "Ena Theatre", showDateLabel: "26 сентября, 19:00", maxSeats: 80, occupiedSeats: 42, isActive: true, isPast: false, isShowDay: true, checkinEnabled: true, hasPublished: true, registrarUsername: "test" };
const analytics = { registered: 42, capacity: 80, cancelledRegistrations: 2, confirmed: 30, arrived: 20, checkinEnabled: true, feedbackEnabled: true, feedbackCount: 0, averageRating: 0, ratingDistribution: {}, occupancyRate: 52, cancellationRate: 4, attendanceRate: 48, dailyRegistrationRate: 3, projectedAttendance: 60, recommendation: "Можно повторить анонс", sources: [], comments: [], commentsLimit: 100 };
try {
  for (const theme of ["light", "dark"]) {
    const page = await browser.newPage({ viewport: { width: 390, height: 844 }, reducedMotion: "reduce" });
    await page.route("**/telegram-web-app.js*", (route) => route.fulfill({ contentType: "application/javascript", body: `window.Telegram={WebApp:{initData:'visual-test',colorScheme:'${theme}',themeParams:{},ready(){},expand(){},onEvent(){},offEvent(){},setHeaderColor(){},setBackgroundColor(){},setBottomBarColor(){}}};` }));
    await page.addInitScript((theme) => { localStorage.setItem("miniapp-theme", theme); localStorage.setItem("miniapp-onboarding-v1", "done"); }, theme);
    await page.route("**/api/**", async (route) => {
      const path = new URL(route.request().url()).pathname;
      const data = path.endsWith("/me") ? { id: 1, role: "admin", firstName: "Тест" }
        : path.endsWith("/options") ? { teams: [], venues: [], adChannels: [] }
        : path.endsWith("/attention") ? { items: [] }
        : path.endsWith("/shows") ? { items: [show], hasMore: false, nextCursor: null }
        : path.endsWith("/shows/1") ? show
        : path.endsWith("/analytics") ? analytics
        : path.endsWith("/checkin") ? { id: 1, title: show.title, mode: "named", reportEvery: 10, arrived: 20, unidentified: 0, booked: 42, remaining: 22, percent: 48, items: [{ kind: "registration", id: 1, name: "Очень длинное имя зрителя для проверки", booked: 3, arrived: 1 }] }
        : { items: [] };
      await route.fulfill({ json: data });
    });
    await page.goto(process.env.VISUAL_URL || "http://127.0.0.1:5173/app/");
    await page.getByRole("heading", { name: "Мои афиши" }).waitFor();
    await page.locator(".show-card").waitFor();
    await page.evaluate(() => document.fonts.ready);
    for (const screen of ["shows", "settings", "show", "analytics", "checkin"]) {
      if (screen === "settings") { await page.getByRole("button", { name: "Настройки", exact: true }).click(); await page.getByRole("tab", { name: "Системная" }).waitFor(); }
      if (screen === "show") { await page.getByRole("button", { name: "Афиши", exact: true }).last().click(); await page.locator(".show-card-main").click(); await page.getByRole("button", { name: "Шоу", exact: true }).waitFor(); }
      if (screen === "analytics") { await page.getByRole("button", { name: "Аналитика", exact: true }).last().click(); await page.getByText("Прогноз", { exact: true }).waitFor(); }
      if (screen === "checkin") {
        await page.getByRole("button", { name: "Вход", exact: true }).last().click();
        await page.getByLabel("Поиск зрителя").waitFor();
        const onTop = await page.getByLabel("Поиск зрителя").evaluate((input) => {
          const rect = input.getBoundingClientRect();
          return input.contains(document.elementFromPoint(rect.left + 5, rect.top + 5));
        });
        if (!onTop) throw new Error("Check-in screen is obscured by another screen");
      }
      const layout = await page.evaluate(() => {
        const menu = [...document.querySelectorAll(".bottom-action-navigation")].findLast((node) => node.getClientRects().length);
        return { overflow: document.documentElement.scrollWidth > innerWidth, bottom: menu?.getBoundingClientRect().bottom, height: innerHeight };
      });
      if (layout.overflow || (screen !== "checkin" && (!layout.bottom || layout.bottom > layout.height))) throw new Error(`${theme}/${screen}: invalid layout ${JSON.stringify(layout)}`);
      const filename = `${theme}-${screen}.png`;
      const screenshot = await page.screenshot({ path: `${output}/${filename}`, fullPage: true });
      if (process.env.VISUAL_BASELINES) await compareBaseline(resolve(process.env.VISUAL_BASELINES, filename), screenshot, process.env.UPDATE_VISUAL_BASELINES === "1");
    }
    await page.close();
  }
  console.log(`Visual smoke passed; screenshots: ${output}`);
} finally { await browser.close(); }
