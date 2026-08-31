export interface EmptyStateProps {
  /** Says what would fill it — e.g. "No students yet. Share the key 7K4P92." */
  message: string;
}

export function EmptyState({ message }: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center gap-2 rounded-lg border border-dashed border-slate-300 p-6 text-center">
      <p className="text-sm text-slate-600">{message}</p>
    </div>
  );
}
