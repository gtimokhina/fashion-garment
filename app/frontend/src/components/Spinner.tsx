export function Spinner({ className = "h-8 w-8 border-2" }: { className?: string }) {
  return (
    <span
      className={`inline-block animate-spin rounded-full border-zinc-200 border-t-zinc-800 dark:border-zinc-700 dark:border-t-zinc-200 ${className}`}
      role="status"
      aria-label="Loading"
    />
  );
}
