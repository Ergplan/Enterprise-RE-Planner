"use client";

import { useState } from "react";

// Sign in by email link (Stage 8). The link works once, for 15 minutes.
export default function LoginPage() {
  const [email, setEmail] = useState("");
  const [state, setState] = useState<"idle" | "busy" | "sent">("idle");
  const [dev, setDev] = useState<string | null>(null);
  const [error, setError] = useState("");
  async function go() {
    setState("busy");
    setError("");
    const next = new URLSearchParams(window.location.search).get("next") ?? "/plan/intake";
    try {
      const r = await fetch("/api/auth/request", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ email, next }) });
      if (!r.ok) throw new Error(r.status === 422 ? "That does not look like an email address." : r.status === 503 ? "Sign-in mail is not set up on this server yet. Ask jouleWise for a sign-in link." : `${r.status}`);
      const d = (await r.json()) as { sent: boolean; dev_link: string | null };
      setDev(d.dev_link);
      setState("sent");
    } catch (e) {
      setError((e as Error).message);
      setState("idle");
    }
  }
  return (
    <section className="eg-card ep-panel" style={{ maxWidth: 520 }}>
      <div className="eg-overline">jouleWise</div>
      <h1 className="eg-h1">Sign in</h1>
      {state === "sent" ? (
        <>
          <p>We sent a sign-in link to <b>{email}</b>. It works once, for 15 minutes.</p>
          {dev && <p className="ep-small eg-muted">Development: no mail server is set up. <a href={dev}>Open the link</a>.</p>}
        </>
      ) : (
        <>
          <p className="eg-muted">Your email is all we need. jouleWise staff sign in with their joulewise.in address.</p>
          <div className="ep-row">
            <span className="eg-input" style={{ flex: 1 }}><input type="email" aria-label="Email" placeholder="you@company.in" value={email}
              onChange={(e) => setEmail(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") void go(); }} /></span>
            <button className="eg-btn eg-btn--primary" disabled={state === "busy" || !email.includes("@")} onClick={go}>Send the link</button>
          </div>
        </>
      )}
      {error && <p className="ep-error">{error}</p>}
    </section>
  );
}
