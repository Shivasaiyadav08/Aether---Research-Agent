import { cn } from "@/lib/utils";

export function BrandMark({ className }: { className?: string }) {
  return (
    <svg
      className={cn("crebry-mark aether-mark", className)}
      width="28"
      height="28"
      viewBox="0 0 28 28"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden="true"
    >
      {/* Outer cerebral orbit arc (C-glyph) */}
      <path
        d="M20.5 7.5C18.8 5.3 16.1 4 13 4C7.5 4 3 8.5 3 14C3 19.5 7.5 24 13 24C16.1 24 18.8 22.7 20.5 20.5"
        stroke="currentColor"
        strokeWidth="2.2"
        strokeLinecap="round"
      />
      {/* Inner evidence focal core */}
      <circle cx="13" cy="14" r="2.5" fill="currentColor" />
      {/* Research synthesis ray */}
      <path
        d="M16.5 14H23"
        stroke="currentColor"
        strokeWidth="2.2"
        strokeLinecap="round"
      />
    </svg>
  );
}

export function Brand({ className }: { className?: string }) {
  return (
    <span className={cn("wordmark", className)}>
      <BrandMark />
      <strong>Crebry</strong>
      <span>The Research Agent</span>
    </span>
  );
}
