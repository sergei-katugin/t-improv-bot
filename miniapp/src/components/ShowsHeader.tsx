import { TelegramTabs } from "./TelegramTabs";
import { PageHeader } from "./PageHeader";

function FilterIcon() {
  return <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 6h16M7 12h10M10 18h4" /></svg>;
}

export function ShowsHeader({ status, onStatusChange, filtersOpened, activeFilters, onToggleFilters }: {
  status: "upcoming" | "past";
  onStatusChange: (status: "upcoming" | "past") => void;
  filtersOpened: boolean;
  activeFilters: number;
  onToggleFilters: () => void;
}) {
  return <div className="shows-header"><PageHeader title="Мои афиши" /><div className="page-tabs-header">
    <TelegramTabs value={status} onChange={onStatusChange} label="Период афиш"
      items={[{ value: "upcoming", label: "Будущие" }, { value: "past", label: "Прошедшие" }]} />
    <div className="header-actions">
      <button className={`header-action${activeFilters ? " is-active" : ""}`} onClick={onToggleFilters} aria-label={`Фильтры${activeFilters ? `: выбрано ${activeFilters}` : ""}`} aria-expanded={filtersOpened}>
        <FilterIcon />
        {Boolean(activeFilters) && <span className="filter-indicator" />}
      </button>
    </div>
  </div></div>;
}
