import type { ReactNode } from "react";
import { DateTimePicker } from "@mantine/dates";
import "dayjs/locale/ru";

export function AppDateTimePicker({ label, description, value, onChange, maxDate, required = false, clearable = false }: {
  label: string; description?: ReactNode; value: string;
  onChange: (value: string) => void; maxDate?: string;
  required?: boolean; clearable?: boolean;
}) {
  return <DateTimePicker
    required={required}
    size="lg"
    dropdownType="modal"
    label={label}
    description={description}
    placeholder="Выбери дату и время"
    valueFormat="D MMMM YYYY, HH:mm"
    locale="ru"
    minDate={new Date().toISOString().slice(0, 10)}
    maxDate={maxDate?.slice(0, 10) || undefined}
    value={value.replace("T", " ")}
    onChange={(next) => onChange(next?.replace(" ", "T") ?? "")}
    timePickerProps={{ minutesStep: 5 }}
    clearable={clearable}
    className="large-date-picker"
  />;
}
