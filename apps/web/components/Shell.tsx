"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";
import { ErgOSMount } from "./ErgOSMount";

// The journey: inputs, results, the plan to share and audit. Detail pages (today's bill rebuilt,
// landed costs per slot) are reached from the results.
const JOURNEY: { n: number; label: string; href: string }[] = [
  { n: 1, label: "Inputs", href: "/evaluate" },
  { n: 2, label: "Results", href: "/results" },
  { n: 3, label: "Share and audit", href: "/plan/report" },
];

const ANALYST: { label: string; href: string; icon: string }[] = [
  { label: "Rulebooks", href: "/rulebooks", icon: "layers" },
  { label: "Proposed changes", href: "/proposals", icon: "check" },
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
  // who is signed in; in production a signed-out visitor is sent to /login (the shared plan stays open)
  const [me, setMe] = useState<{ email: string | null; role: string; signed_in: boolean; required: boolean } | null>(null);
  useEffect(() => {
    fetch("/api/auth/me")
      .then((r) => (r.ok ? r.json() : null))
      .then((m) => {
        if (!m) return;
        setMe(m);
        try {
          if (m.signed_in && m.role === "analyst") localStorage.setItem("ergplan-analyst", m.email);
          else if (m.required) localStorage.removeItem("ergplan-analyst");
        } catch {
          /* storage may be unavailable */
        }
        const open = path.startsWith("/login") || path.startsWith("/account") || path.startsWith("/p/") || path.startsWith("/documents");
        if (m.required && !m.signed_in && !open) window.location.replace(`/login?next=${encodeURIComponent(path + window.location.search)}`);
      })
      .catch(() => undefined);
  }, [path]);
  async function signOut() {
    await fetch("/api/auth/logout", { method: "POST" });
    try {
      localStorage.removeItem("ergplan-analyst");
    } catch {
      /* storage may be unavailable */
    }
    window.location.replace("/login");
  }
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
          <Link className="eg-nav__item" href="/" aria-current={path === "/" ? "page" : undefined}>
            <span data-icon="home" data-size="19"></span>
            Evaluations
          </Link>
          <div className="eg-overline eg-nav__group">This evaluation</div>
          {JOURNEY.map((s) => (
            <Link key={s.n} className="eg-nav__item ep-step" href={site ? `${s.href}?c=${site}` : s.href} aria-current={current(s.href) ?? (s.href === "/plan/report" && path.startsWith("/plan/") ? "page" : undefined)}>
              <span className="ep-step__n">{s.n}</span>
              {s.label}
            </Link>
          ))}
          <Link className="eg-nav__item" href="/bills" aria-current={current("/bills")}>
            <span data-icon="receipt" data-size="19"></span>
            Your bills
          </Link>
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
            {me?.signed_in ? (
              <span className="ep-row ep-small"><span className="eg-muted">{me.email}{me.role === "analyst" ? " · jouleWise" : ""}</span>
                <a className="eg-btn eg-btn--ghost eg-btn--sm" href="/account">Password</a>
                <button className="eg-btn eg-btn--ghost eg-btn--sm" onClick={signOut}>Sign out</button></span>
            ) : me?.required ? <a className="eg-btn eg-btn--ghost eg-btn--sm" href="/login">Sign in</a> : null}
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
