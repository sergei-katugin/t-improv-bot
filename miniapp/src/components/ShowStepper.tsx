interface ShowStepperProps {
  active: number;
  labels: readonly string[];
  allowAllSteps?: boolean;
  onStepChange?: (step: number) => void;
}

export function ShowStepper({ active, labels, allowAllSteps = false, onStepChange }: ShowStepperProps) {
  return <nav className="show-stepper" aria-label="Шаги создания афиши">
    {labels.map((label, index) => <div className="show-stepper-item" key={label}>
      <button
        type="button"
        className="show-stepper-dot"
        data-state={index === active ? "active" : index < active ? "complete" : "pending"}
        aria-current={index === active ? "step" : undefined}
        aria-label={`Шаг ${index + 1}: ${label}`}
        disabled={!onStepChange || (!allowAllSteps && index > active)}
        onClick={() => onStepChange?.(index)}
      >
        <span>{index + 1}</span>
      </button>
      {index < labels.length - 1 && <span className="show-stepper-line" data-complete={index < active} />}
    </div>)}
  </nav>;
}
