import Link from "next/link";
import { ResearchApp } from "@/components/research-app";
import { auth } from "@clerk/nextjs/server";
import { redirect } from "next/navigation";
import { AuthShell } from "@/components/auth-shell";
export default async function ResearchPage() {
  if (
    !process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY ||
    !process.env.CLERK_SECRET_KEY
  )
    return (
      <AuthShell signingUp>
        <div className="auth-setup">
          <span className="eyebrow">Workspace access</span>
          <h2>Your private lab needs Clerk.</h2>
          <p>
            The application owner must add Clerk keys to frontend/.env.local and
            the backend environment, then restart both servers. Authentication
            stays closed until setup is complete.
          </p>
          <Link className="landing-cta" href="/">
            Back to Crebry
          </Link>
        </div>
      </AuthShell>
    );
  const { userId } = await auth();
  if (!userId) redirect("/sign-in");
  return <ResearchApp key={userId} userId={userId} />;
}
