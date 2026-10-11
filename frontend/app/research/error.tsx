"use client";

import Link from "next/link";
import { ArrowLeft, RefreshCw } from "lucide-react";
import { BrandMark } from "@/components/brand";
import { Button } from "@/components/ui/button";

export default function Error({
  retry,
}: {
  error: Error & { digest?: string };
  retry: () => void;
}) {
  return (
    <main className="route-error">
      <BrandMark />
      <span className="eyebrow">Workspace unavailable</span>
      <h1>Let’s reconnect your research.</h1>
      <p>
        We couldn’t open the workspace. Try again to pick up where you left off.
      </p>
      <div>
        <Button onClick={retry}>
          <RefreshCw size={14} /> Try again
        </Button>
        <Link className="button button-ghost" href="/">
          <ArrowLeft size={14} /> Back to Aether
        </Link>
      </div>
    </main>
  );
}
