"use client";

import { useState } from "react";

function nextPath(): string {
  const n = new URLSearchParams(window.location.search).get("next") ?? "/plan/intake";
  return n.startsWith("/") ? n : "/plan/intake";
}

function remember(me: { email: string; role: string }) {
  try {
    if (me.role === "analyst") localStorage.setItem("ergplan-analyst", me.email);
    else localStorage.removeItem("ergplan-analyst");
  } catch {
    /* storage may be unavailable */
  }
}

// Sign in with email and password; first time (or a forgotten password), an emailed one-time link.
export default function LoginPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [mode, setMode] = useState<"password" | "link">("password");
  const [state, setState] = useState<"idle" | "busy" | "sent">("idle");
  const [dev, setDev] = useState<string | null>(null);
  const [error, setError] = useState("");

  async function signIn() {
    setState("busy");
    setError("");
    try {
      const r = await fetch("/api/auth/login", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ email, password }) });
      if (!r.ok) {
        const d = (await r.json().catch(() => ({}))) as { detail?: string };
        throw new Error(r.status === 422 ? "That does not look like an email address." : d.detail ?? `${r.status}`);
      }
      remember((await r.json()) as { email: string; role: string });
      window.location.replace(nextPath());
    } catch (e) {
      setError((e as Error).message);
      setState("idle");
    }
  }

  async function sendLink() {
    setState("busy");
    setError("");
    try {
      const r = await fetch("/api/auth/request", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ email, next: nextPath() }) });
      if (!r.ok) throw new Error(r.status === 422 ? "That does not look like an email address." : r.status === 503 ? "Sign-in mail is not set up on this server yet. Ask jouleWise for a sign-in link." : `${r.status}`);
      const d = (await r.json()) as { sent: boolean; dev_link: string | null };
      setDev(d.dev_link);
      setState("sent");
    } catch (e) {
      setError((e as Error).message);
      setState("idle");
    }
  }

  const ready = email.includes("@") && (mode === "link" || password.length > 0);
  return (
    <section className="eg-card ep-panel" style={{ maxWidth: 520 }}>
      <div className="eg-overline">jouleWise</div>
      <h1 className="eg-h1">Sign in</h1>
      {state === "sent" ? (
        <>
          <p>We sent a sign-in link to <b>{email}</b>. It works once, for 15 minutes; you can set a password after it.</p>
          {dev && <p className="ep-small eg-muted">Development: no mail server is set up. <a href={dev}>Open the link</a>.</p>}
        </>
      ) : (
        <form className="ep-form" onSubmit={(e) => { e.preventDefault(); if (ready) void (mode === "password" ? signIn() : sendLink()); }}>
          <label className="ep-field">
            <span className="ep-small eg-muted">Email</span>
            <span className="eg-input"><input type="email" autoComplete="username" aria-label="Email" placeholder="you@company.in" value={email} onChange={(e) => setEmail(e.target.value)} /></span>
          </label>
          {mode === "password" && (
            <label className="ep-field">
              <span className="ep-small eg-muted">Password</span>
              <span className="eg-input"><input type="password" autoComplete="current-password" aria-label="Password" value={password} onChange={(e) => setPassword(e.target.value)} /></span>
            </label>
          )}
          <div className="ep-row">
            <button className="eg-btn eg-btn--primary" type="submit" disabled={state === "busy" || !ready}>
              {mode === "password" ? "Sign in" : "Email me a link"}
            </button>
            <button className="eg-btn eg-btn--ghost eg-btn--sm" type="button" onClick={() => { setMode(mode === "password" ? "link" : "password"); setError(""); }}>
              {mode === "password" ? "First time, or forgot your password?" : "Sign in with a password"}
            </button>
          </div>
        </form>
      )}
      {error && <p className="ep-error">{error}</p>}
    </section>
  );
}
