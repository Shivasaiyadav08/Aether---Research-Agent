import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}
export function formatTime(ms: number) {
  return `${(ms / 1000).toFixed(1)}s`;
}
export function formatSize(bytes: number) {
  return bytes < 1024 * 1024
    ? `${Math.ceil(bytes / 1024)} KB`
    : `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

export function formatModelPrice(
  value: string | undefined,
  direction: "input" | "output",
) {
  const price = Number(value);
  // Some routing models report a negative sentinel instead of a fixed price.
  if (value === undefined || !Number.isFinite(price) || price < 0)
    return "Variable pricing";
  return `$${(price * 1e6).toFixed(2)} / M ${direction}`;
}
