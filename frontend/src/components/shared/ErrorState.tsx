export interface ErrorStateProps {
  /** What failed, in plain language — never a raw error string/stack. */
  message: string;
  onRetry: () => void;
}

export function ErrorState({ message, onRetry }: ErrorStateProps) {
  return (
    <div className="flex flex-col items-center gap-3 rounded-lg border border-border bg-surface2 p-6 text-center">
      <p className="text-sm text-ink-secondary">{message}</p>
      <button
        type="button"
        onClick={onRetry}
        className="min-h-[44px] rounded-lg border border-border-strong px-4 text-sm font-medium text-ink-primary"
      >
        Try again
      </button>
    </div>
  );
}
