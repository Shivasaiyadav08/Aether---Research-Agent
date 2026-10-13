import type { Metadata } from "next";
import { ClerkProvider } from "@clerk/nextjs";
import { shadcn } from "@clerk/ui/themes";
import { ThemeProvider } from "@/components/theme-provider";
import { ResearchSession } from "@/components/research-session";
import "@xyflow/react/dist/style.css";
import "./globals.css";
import "./design-tokens.css";
import "./workspace.css";
import "./landing.css";

export const metadata: Metadata = {
  title: "Crebry — The Research Agent",
  description:
    "Autonomous research agent powered by corrective retrieval, knowledge synthesis, and verified citations.",
  icons: {
    icon: "/icon.svg",
    shortcut: "/icon.svg",
    apple: "/crebry-logo.svg",
  },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body>
        {process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY &&
        process.env.CLERK_SECRET_KEY ? (
          <ClerkProvider
            appearance={{
              theme: shadcn,
              variables: {
                colorPrimary: "var(--primary)",
                colorPrimaryForeground: "var(--primary-foreground)",
                colorBackground: "var(--card)",
                colorForeground: "var(--card-foreground)",
                colorMuted: "var(--surface)",
                colorMutedForeground: "var(--muted)",
                colorInput: "var(--surface)",
                colorInputForeground: "var(--text)",
                colorBorder: "var(--border)",
                borderRadius: "8px",
                fontFamily: 'Geist, "Segoe UI", sans-serif',
              },
              elements: {
                card: {
                  boxShadow: "0 1px 3px rgba(0,0,0,0.06), 0 1px 2px rgba(0,0,0,0.04)",
                  border: "1px solid var(--border)",
                  background: "var(--card)",
                },
                cardBox: { boxShadow: "none" },
                popoverBox: {
                  boxShadow: "0 10px 25px -5px rgba(0,0,0,0.1), 0 8px 10px -6px rgba(0,0,0,0.1)",
                  border: "1px solid var(--border)",
                  background: "var(--popover)",
                },
                formButtonPrimary: {
                  background: "var(--primary)",
                  color: "var(--primary-foreground)",
                  boxShadow: "none",
                },
              },
            }}
            localization={{
              signIn: {
                start: {
                  title: "Sign in to Crebry",
                  titleCombined: "Sign in to Crebry",
                },
              },
              signUp: {
                start: {
                  title: "Create your Crebry account",
                  titleCombined: "Create your Crebry account",
                },
              },
            }}
            signInUrl="/sign-in"
            signUpUrl="/sign-up"
            signInFallbackRedirectUrl="/research"
            signUpFallbackRedirectUrl="/research"
          >
            <ResearchSession />
            <ThemeProvider>{children}</ThemeProvider>
          </ClerkProvider>
        ) : (
          <ThemeProvider>{children}</ThemeProvider>
        )}
      </body>
    </html>
  );
}
