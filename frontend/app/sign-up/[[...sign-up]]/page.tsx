import { SignUp } from "@clerk/nextjs";
import Link from "next/link";
import { AuthShell } from "@/components/auth-shell";
export default function Page() {
  return (
    <AuthShell signingUp>
      {process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY &&
      process.env.CLERK_SECRET_KEY ? (
        <SignUp />
      ) : (
        <div className="auth-setup">
          <span className="eyebrow">Create your account</span>
          <h2>Your research starts here.</h2>
          <p>Add Clerk application keys to enable secure accounts.</p>
          <Link href="/" className="landing-cta">
            Back to Crebry
          </Link>
        </div>
      )}
    </AuthShell>
  );
}
