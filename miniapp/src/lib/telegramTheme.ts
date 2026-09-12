const tokens = {
  "--app-bg": ["bg_color"],
  "--app-text": ["text_color"],
  "--surface": ["section_bg_color", "secondary_bg_color", "bg_color"],
  "--muted": ["subtitle_text_color", "hint_color"],
  "--accent": ["accent_text_color", "button_color", "link_color"],
  "--app-header-bg": ["header_bg_color", "bg_color"],
  "--app-button-bg": ["button_color"],
  "--app-button-text": ["button_text_color"],
  "--mantine-color-text": ["text_color"],
  "--mantine-color-dimmed": ["subtitle_text_color", "hint_color"],
} as const;

export function applyTelegramTheme(params: Record<string, string | undefined> | undefined) {
  const root = document.documentElement;
  for (const [token, keys] of Object.entries(tokens)) {
    const color = keys.map((key) => params?.[key]).find((value) => value && /^#[\da-f]{6}$/i.test(value));
    if (color) root.style.setProperty(token, color);
    else root.style.removeProperty(token);
  }
  if (params) root.style.setProperty("--surface-strong", "color-mix(in srgb, var(--surface) 88%, var(--app-text))");
  else root.style.removeProperty("--surface-strong");
}
