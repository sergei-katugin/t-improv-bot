import type { Show } from "../types";
import { BottomActionBar, BottomNavAction } from "./BottomActionBar";

export type ShowNavigationItem = "show" | "edit" | "announcement" | "analytics" | "registration" | "more";

export function ShowNavigation({ show, active, onShow, onEdit, onAnnouncement, onAnalytics, onRegistration, onMore }: {
  show: Show;
  active?: ShowNavigationItem;
  onShow: () => void;
  onEdit: () => void;
  onAnnouncement: () => void;
  onAnalytics: () => void;
  onRegistration: () => void;
  onMore: () => void;
}) {
  return <BottomActionBar navigation>
    <BottomNavAction icon="shows" label="Шоу" active={active === "show"} onClick={onShow} />
    {!show.isPast && <BottomNavAction icon="edit" label="Изменить" active={active === "edit"} onClick={onEdit} />}
    {!show.isPast && !show.hasPublished && <BottomNavAction icon="announce" label="Анонс" active={active === "announcement"} onClick={onAnnouncement} />}
    {(show.isPast || show.hasPublished) && <BottomNavAction icon="analytics" label="Аналитика" active={active === "analytics"} onClick={onAnalytics} />}
    {!show.isPast && <BottomNavAction icon="link" label="Ссылка" active={active === "registration"} onClick={onRegistration} />}
    <BottomNavAction icon="more" label="Ещё" active={active === "more"} onClick={onMore} />
  </BottomActionBar>;
}
