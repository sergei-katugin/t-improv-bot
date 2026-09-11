import React from "react";
import type { ShowFormValue } from "../types";

type ShowFormDraft = {
  version: 1;
  value: ShowFormValue;
  venueId: string | null;
  activeStep: number;
};

export function showFormDraftKey(showId?: number): string {
  return `t-impro:show-draft:${showId ?? "new"}`;
}

export function readShowFormDraft(key: string, fallback: ShowFormValue): ShowFormDraft | null {
  try {
    const parsed = JSON.parse(localStorage.getItem(key) ?? "null") as Partial<ShowFormDraft> | null;
    if (!parsed || parsed.version !== 1 || !parsed.value || typeof parsed.value !== "object") return null;
    const value = { ...fallback };
    for (const field of Object.keys(fallback) as (keyof ShowFormValue)[]) {
      if (typeof parsed.value[field] !== typeof fallback[field]) return null;
      Object.assign(value, { [field]: parsed.value[field] });
    }
    const venueId = parsed.venueId;
    const activeStep = parsed.activeStep;
    if (venueId !== null && typeof venueId !== "string") return null;
    if (!Number.isInteger(activeStep) || activeStep! < 0 || activeStep! > 3) return null;
    return { version: 1, value, venueId, activeStep: activeStep! };
  } catch {
    return null;
  }
}

export function clearShowFormDraft(key: string): void {
  localStorage.removeItem(key);
}

export function useShowFormDraft(key: string, enabled: boolean, value: ShowFormValue, venueId: string | null, activeStep: number): void {
  React.useEffect(() => {
    if (!enabled) return;
    const timer = window.setTimeout(() => {
      try {
        localStorage.setItem(key, JSON.stringify({ version: 1, value, venueId, activeStep } satisfies ShowFormDraft));
      } catch { /* A full or disabled storage must not break the form. */ }
    }, 300);
    return () => window.clearTimeout(timer);
  }, [activeStep, enabled, key, value, venueId]);
}
