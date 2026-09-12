# Mobile visual smoke

Start `npm run dev`, then run `node scripts/visual-smoke.mjs`.
Requires Playwright with Chromium. `PLAYWRIGHT_MODULE_PATH` can select an
absolute bundled Playwright entry point. `VISUAL_URL` and `VISUAL_OUTPUT`
override the frontend URL and screenshot directory.

Mocks API requests and captures show list/settings in light/dark themes at
390 × 844, checking horizontal overflow and bottom-menu placement.
Screenshots are for inspection, not approved pixel-regression baselines.
Real Telegram chrome, keyboards, resume and swipes still require device QA.

For pixel-exact PNG comparison set `VISUAL_BASELINES` to a baseline directory.
Create/update it only after inspection with `UPDATE_VISUAL_BASELINES=1`.
Without that flag, missing or changed snapshots fail the check; actual images
remain in `VISUAL_OUTPUT`. Use the same browser version, OS and fonts.
Installed Chrome can be selected with `VISUAL_BROWSER_CHANNEL=chrome`.
Test baseline handling with `node --test scripts/screenshot-baseline.node-check.mjs`.
