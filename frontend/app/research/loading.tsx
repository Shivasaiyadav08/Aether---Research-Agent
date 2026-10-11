import { BrandMark } from "@/components/brand";

export default function Loading() {
  return (
    <main
      className="workspace-loading"
      aria-busy="true"
      aria-label="Loading research workspace"
    >
      <aside>
        <BrandMark />
        <div className="skeleton skeleton-wide" />
        <div className="skeleton" />
        <div className="skeleton" />
      </aside>
      <section>
        <div className="loading-topbar">
          <span>Opening your workspace</span>
        </div>
        <div className="loading-reading">
          <div className="skeleton skeleton-title" />
          <div className="skeleton skeleton-wide" />
          <div className="skeleton" />
          <div className="skeleton skeleton-composer" />
        </div>
      </section>
    </main>
  );
}
