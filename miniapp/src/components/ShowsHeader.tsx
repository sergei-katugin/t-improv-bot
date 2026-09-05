import { Badge } from "@mantine/core";

function FilterIcon() {
  return <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 6h16M7 12h10M10 18h4" /></svg>;
}

function SettingsIcon() {
  return <svg viewBox="0 0 24 24" aria-hidden="true">
    <path d="M12 8.5a3.5 3.5 0 1 0 0 7 3.5 3.5 0 0 0 0-7Z" />
    <path d="M19.4 13.5a7.8 7.8 0 0 0 0-3l1.7-1.3-2-3.4-2 .8a8 8 0 0 0-2.6-1.5L14.2 3h-4.4l-.3 2.1a8 8 0 0 0-2.6 1.5l-2-.8-2 3.4 1.7 1.3a7.8 7.8 0 0 0 0 3l-1.7 1.3 2 3.4 2-.8a8 8 0 0 0 2.6 1.5l.3 2.1h4.4l.3-2.1a8 8 0 0 0 2.6-1.5l2 .8 2-3.4-1.7-1.3Z" />
  </svg>;
}

export function ShowsHeader({ demo, filtersOpened, activeFilters, onToggleFilters, onOpenSettings }: {
  demo: boolean;
  filtersOpened: boolean;
  activeFilters: number;
  onToggleFilters: () => void;
  onOpenSettings: () => void;
}) {
  return <header className="app-header">
    <div>
      <div className="brand">T·IMPRO</div>
      <h1>Мои афиши</h1>
      {demo && <Badge mt={8} color="gray" variant="light">Демо-данные · API отключён</Badge>}
    </div>
    <div className="header-actions">
      <button className={`header-action${activeFilters ? " is-active" : ""}`} onClick={onToggleFilters} aria-label={`Фильтры${activeFilters ? `: выбрано ${activeFilters}` : ""}`} aria-expanded={filtersOpened}>
        <FilterIcon />
        {Boolean(activeFilters) && <span className="filter-indicator" />}
      </button>
      <button className="header-action" onClick={onOpenSettings} aria-label="Открыть настройки"><SettingsIcon /></button>
    </div>
  </header>;
}
