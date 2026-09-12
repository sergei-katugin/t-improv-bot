import React from "react";
import { Modal } from "@mantine/core";
import { CheckinScreen } from "./CheckinScreen";

export const CheckinNavigation = React.createContext<((showId: number) => void) | null>(null);

export function CheckinProvider({ children }: { children: React.ReactNode }) {
  const [showId, setShowId] = React.useState<number | null>(null);
  return <CheckinNavigation.Provider value={setShowId}>{children}<Modal opened={showId !== null} onClose={() => setShowId(null)} fullScreen title="Вход" zIndex={300} classNames={{ content: "checkin-sheet" }}>{showId !== null && <CheckinScreen key={showId} showId={showId} canConfigure />}</Modal></CheckinNavigation.Provider>;
}
