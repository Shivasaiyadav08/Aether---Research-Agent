import { cn } from "@/lib/utils";

export function BrandMark({ className }: { className?: string }) {
  return (
    <svg
      className={cn("aether-mark", className)}
      width="28"
      height="28"
      viewBox="0 0 28 28"
      fill="none"
      aria-hidden="true"
    >
      <path
        d="M4 23 14 5l10 18M8.5 16h11M11 23l3-5 3 5"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

export function Brand() {
  return (
    <span className="wordmark">
      <BrandMark />
      <strong>aether</strong>
      <span>Research lab</span>
    </span>
  );
}
