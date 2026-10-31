"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";
import { ErgOSMount } from "./ErgOSMount";

// The client journey (plan section 1). Steps light up as their stage ships.
const JOURNEY: { n: number; label: string; href: string; live: boolean }[] = [
  { n: 1, label: "Drop a bill", href: "/plan/intake", live: true },
  { n: 2, label: "Today's cost", href: "/plan/today", live: true },
  { n: 3, label: "Landed costs", href: "/plan/landed", live: true },
  { n: 4, label: "Describe the site", href: "/plan/site", live: true },
  { n: 5, label: "Optimise", href: "/plan/optimise", live: true },
  { n: 6, label: "Your plan", href: "/plan/report", live: true },
];

const ANALYST: { label: string; href: string; icon: string }[] = [
  { label: "Rulebooks", href: "/rulebooks", icon: "layers" },
  { label: "Documents", href: "/documents", icon: "file" },
  { label: "Market prices", href: "/prices", icon: "trend" },
  { label: "Settlement", href: "/settlement", icon: "battery" },
];

function toggleTheme() {
  const el = document.documentElement;
  el.dataset.theme = el.dataset.theme === "light" ? "dark" : "light";
  try {
    localStorage.setItem("ergplan-theme", el.dataset.theme);
  } catch {
    /* storage may be unavailable */
  }
}

const SITE_KEY = "ergplan-connection";

export function Shell({ children }: { children: ReactNode }) {
  const path = usePathname() ?? "/";
  // the site the journey is on: remembered from ?c= so every step of the rail opens it
  const [site, setSite] = useState("");
  useEffect(() => {
    const c = new URLSearchParams(window.location.search).get("c");
    try {
      if (c) localStorage.setItem(SITE_KEY, c);
      setSite(c ?? localStorage.getItem(SITE_KEY) ?? "");
    } catch {
      setSite(c ?? "");
    }
  }, [path]);
  if (path.startsWith("/p/")) return <main className="ep-public">{children}</main>; // the shared plan: no rail
  const current = (href: string) => (path === href || path.startsWith(href + "/") ? "page" : undefined);
  return (
    <div className="ep-shell">
      <aside className="eg-side ep-side" aria-label="Navigation">
        <div className="eg-brand">
          <Link href="/" aria-label="ergPLAN home" style={{ textDecoration: "none" }}>
            <span className="eg-wordmark">
              erg<i>PLAN</i>
            </span>
          </Link>
        </div>
        <nav className="eg-nav">
          <div className="eg-overline eg-nav__group">Plan</div>
          {JOURNEY.map((s) => (
            <Link key={s.n} className="eg-nav__item ep-step" href={site && s.n > 1 ? `${s.href}?c=${site}` : s.href} aria-current={current(s.href)}
              aria-disabled={s.live ? undefined : "true"} tabIndex={s.live ? undefined : -1}>
              <span className="ep-step__n">{s.n}</span>
              {s.label}
            </Link>
          ))}
          <div className="eg-overline eg-nav__group">jouleWise</div>
          {ANALYST.map((a) => (
            <Link key={a.href} className="eg-nav__item" href={a.href} aria-current={current(a.href)}>
              <span data-icon={a.icon} data-size="19"></span>
              {a.label}
            </Link>
          ))}
        </nav>
        <div className="eg-side__foot">
          <img className="ep-brand-logo ep-logo-dark" src="/brand/joulewise-dark.svg" alt="jouleWise" />
          <img className="ep-brand-logo ep-logo-light" src="/brand/joulewise-light.svg" alt="jouleWise" />
          Green power planning
        </div>
      </aside>
      <main className="ep-content">
        <header className="eg-topbar">
          <div className="eg-crumbs">
            jouleWise <span data-icon="chevron-right" data-size="14"></span> <b>ergPLAN</b>
          </div>
          <div className="eg-topbar__end">
            <button className="eg-icon-btn eg-icon-btn--sm" aria-label="Switch theme" onClick={toggleTheme}>
              <span data-icon="moon" data-size="18"></span>
            </button>
          </div>
        </header>
        {children}
      </main>
      <ErgOSMount />
    </div>
  );
}
