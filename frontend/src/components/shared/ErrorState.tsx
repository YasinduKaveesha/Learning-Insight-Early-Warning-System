export interface ErrorStateProps {
  /** What failed, in plain language — never a raw error string/stack. */
  message: string;
  onRetry: () => void;
}

export function ErrorState({ message, onRetry }: ErrorStateProps) {
  return (
    <div className="flex flex-col items-center gap-3 rounded-lg border border-slate-200 bg-slate-50 p-6 text-center">
      <p className="text-sm text-slate-600">{message}</p>
      <button
        type="button"
        onClick={onRetry}
        className="min-h-[44px] rounded-lg border border-slate-300 px-4 text-sm font-medium text-slate-700"
      >
        Try again
      </button>
    </div>
  );
}
