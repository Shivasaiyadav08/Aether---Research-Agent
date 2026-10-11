"use client";

import { useEffect } from "react";
import { useAuth } from "@clerk/nextjs";
import { setResearchSession } from "@/lib/research-stream";

// The root layout persists through navigation. Clear private state on auth changes,
// rather than when a research view or page unmounts.
export function ResearchSession() {
  const { isLoaded, userId } = useAuth();
  useEffect(() => {
    if (isLoaded) setResearchSession(userId ?? "");
  }, [isLoaded, userId]);
  return null;
}
