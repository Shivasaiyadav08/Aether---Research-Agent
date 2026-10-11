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
  title: "Aether Research Lab — Research with clarity",
  description:
    "A thoughtful research workspace powered by agentic corrective retrieval, local knowledge, and verified source references.",
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
                colorPrimary: "#f5f5f5",
                colorPrimaryForeground: "#090909",
                colorBackground: "#111111",
                colorForeground: "#f5f5f5",
                colorMuted: "#171717",
                colorMutedForeground: "#a3a3a3",
                colorInput: "#171717",
                colorInputForeground: "#f5f5f5",
                colorBorder: "#262626",
                colorDanger: "#d4d4d4",
                borderRadius: "6px",
                fontFamily: 'Geist, "Segoe UI", sans-serif',
              },
              elements: {
                rootBox: { filter: "grayscale(1)" },
                card: { boxShadow: "none", border: "1px solid #262626" },
                cardBox: { boxShadow: "none" },
                formButtonPrimary: { boxShadow: "none" },
              },
            }}
            localization={{
              signIn: {
                start: {
                  title: "Sign in to Aether",
                  titleCombined: "Sign in to Aether",
                },
              },
              signUp: {
                start: {
                  title: "Create your Aether account",
                  titleCombined: "Create your Aether account",
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
