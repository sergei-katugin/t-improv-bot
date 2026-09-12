import type { Show } from "../types";
import { useContext } from "react";
import { CheckinNavigation } from "../features/CheckinNavigation";
import { BottomActionBar, BottomNavAction } from "./BottomActionBar";

export type ShowNavigationItem = "show" | "edit" | "announcement" | "analytics" | "registration" | "more";

export function ShowNavigation({ show, active, onShow, onAnnouncement, onAnalytics, onMore }: {
  show: Show;
  active?: ShowNavigationItem;
  onShow: () => void;
  onEdit: () => void;
  onAnnouncement: () => void;
  onAnalytics: () => void;
  onRegistration: () => void;
  onMore: () => void;
}) {
  const openCheckin = useContext(CheckinNavigation);
  return <BottomActionBar navigation>
    <BottomNavAction icon="shows" label="Шоу" active={active === "show"} onClick={onShow} />
    {show.isShowDay && show.isActive && show.checkinEnabled && <BottomNavAction icon="attendees" label="Вход" onClick={() => openCheckin ? openCheckin(show.id) : onMore()} />}
    <BottomNavAction icon="announce" label="Анонс" active={active === "announcement"} onClick={onAnnouncement} />
    {(show.isPast || show.hasPublished) && <BottomNavAction icon="analytics" label="Аналитика" active={active === "analytics"} onClick={onAnalytics} />}
    <BottomNavAction icon="more" label={show.isPast ? "Настройки" : "Действия"} active={active === "more"} onClick={onMore} />
  </BottomActionBar>;
}
