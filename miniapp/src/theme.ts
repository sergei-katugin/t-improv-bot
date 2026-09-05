import { createTheme } from "@mantine/core";

export const theme = createTheme({
  primaryColor: "gray",
  defaultRadius: "md",
  colors: {
    dark: [
      "#fafafa", "#f5f5f5", "#e5e5e5", "#a3a3a3", "#737373",
      "#525252", "#303030", "#242424", "#171717", "#0f0f0f",
    ],
  },
  fontFamily: 'Inter, ui-sans-serif, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
  headings: { fontFamily: 'Inter, ui-sans-serif, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif' },
});
