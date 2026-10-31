import type { Metadata } from "next";
import Script from "next/script";
import type { ReactNode } from "react";
import { Shell } from "@/components/Shell";
import "./ergplan.css";

export const metadata: Metadata = {
  title: "ergPLAN · jouleWise",
  description: "Landed cost of green power and the RE mix that replaces grid and thermal power, every number sourced.",
};

const THEME_BOOT = `try{var t=localStorage.getItem('ergplan-theme');if(t)document.documentElement.dataset.theme=t}catch(e){}`;

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" data-theme="dark" suppressHydrationWarning>
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link
          rel="stylesheet"
          href="https://fonts.googleapis.com/css2?family=Urbanist:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap"
        />
        <link rel="stylesheet" href="/vendor/harmony/tokens.css" />
        <link rel="stylesheet" href="/vendor/harmony/harmony.css" />
        <script dangerouslySetInnerHTML={{ __html: THEME_BOOT }} />
      </head>
      <body className="eg-stage">
        <Shell>{children}</Shell>
        <Script src="/vendor/harmony/harmony.js" strategy="afterInteractive" />
      </body>
    </html>
  );
}
