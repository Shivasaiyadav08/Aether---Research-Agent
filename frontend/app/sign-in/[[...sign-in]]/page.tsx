import { SignIn } from "@clerk/nextjs";
import Link from "next/link";
import { AuthShell } from "@/components/auth-shell";
export default function Page() {
  return (
    <AuthShell>
      {process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY &&
      process.env.CLERK_SECRET_KEY ? (
        <SignIn />
      ) : (
        <div className="auth-setup">
          <span className="eyebrow">Account access</span>
          <h2>Sign-in is being connected.</h2>
          <p>Add Clerk application keys to enable secure accounts.</p>
          <Link href="/" className="landing-cta">
            Back to Aether
          </Link>
        </div>
      )}
    </AuthShell>
  );
}
