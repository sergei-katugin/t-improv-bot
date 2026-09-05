import { Tabs } from "@mantine/core";

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
  return <header className="page-tabs-header">
    <Tabs value={status} onChange={(value) => onStatusChange(value as "upcoming" | "past")} className="tabs">
      <Tabs.List grow><Tabs.Tab value="upcoming">Будущие</Tabs.Tab><Tabs.Tab value="past">Прошедшие</Tabs.Tab></Tabs.List>
    </Tabs>
    <div className="header-actions">
      <button className={`header-action${activeFilters ? " is-active" : ""}`} onClick={onToggleFilters} aria-label={`Фильтры${activeFilters ? `: выбрано ${activeFilters}` : ""}`} aria-expanded={filtersOpened}>
        <FilterIcon />
        {Boolean(activeFilters) && <span className="filter-indicator" />}
      </button>
    </div>
  </header>;
}
