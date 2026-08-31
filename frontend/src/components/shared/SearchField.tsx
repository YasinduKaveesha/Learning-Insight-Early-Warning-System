import { useId } from "react";

export interface SearchFieldProps {
  label: string;
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  /** Announced via a live region so a screen-reader user hears the count
   * update as they type (plan §9). */
  resultCount?: number;
}

export function SearchField({
  label,
  value,
  onChange,
  placeholder,
  resultCount,
}: SearchFieldProps) {
  const inputId = useId();
  return (
    <div>
      <label htmlFor={inputId} className="sr-only">
        {label}
      </label>
      <input
        id={inputId}
        type="search"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder ?? label}
        className="min-h-[44px] w-full rounded-lg border border-slate-300 px-3 text-base"
      />
      {resultCount !== undefined ? (
        <p role="status" aria-live="polite" className="sr-only">
          {resultCount} result{resultCount === 1 ? "" : "s"}
        </p>
      ) : null}
    </div>
  );
}
