"use client";

import { Moon, Sun } from "lucide-react";
import { useTheme } from "next-themes";

export function LandingThemeToggle() {
  const { resolvedTheme, setTheme } = useTheme();

  return (
    <button
      type="button"
      className="landing-theme-toggle"
      aria-label="Toggle dark and light mode"
      title="Toggle dark and light mode"
      onClick={() => setTheme(resolvedTheme === "dark" ? "light" : "dark")}
    >
      <Sun className="theme-icon-sun" size={16} aria-hidden="true" />
      <Moon className="theme-icon-moon" size={16} aria-hidden="true" />
    </button>
  );
}
