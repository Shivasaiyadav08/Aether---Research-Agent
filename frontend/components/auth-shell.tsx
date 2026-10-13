import Link from "next/link";
import { ArrowLeft, BookOpen } from "lucide-react";
import { Brand } from "@/components/brand";

export function AuthShell({
  children,
  signingUp = false,
}: {
  children: React.ReactNode;
  signingUp?: boolean;
}) {
  return (
    <main className="auth-page">
      <nav className="auth-nav" aria-label="Account navigation">
        <Link href="/" aria-label="Crebry — The Research Agent home">
          <Brand />
        </Link>
        <Link href="/">
          <ArrowLeft size={14} /> Back to Crebry
        </Link>
      </nav>
      <div className="auth-layout">
        <section className="auth-editorial">
          <span className="eyebrow">The Research Agent</span>
          <h1>
            {signingUp ? (
              <>
                A place for your
                <br />
                next big question.
              </>
            ) : (
              <>
                Pick up your thread
                <br />
                of understanding.
              </>
            )}
          </h1>
          <p>
            Your questions, documents, and discoveries. Together in one
            thoughtful workspace.
          </p>
          <small>
            <BookOpen size={15} /> Made for curiosity. Grounded in evidence.
          </small>
        </section>
        <div className="auth-form">{children}</div>
      </div>
    </main>
  );
}
