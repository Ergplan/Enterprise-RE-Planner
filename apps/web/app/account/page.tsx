"use client";

import { useEffect, useState } from "react";

// Set a password (after signing in by link) or change it. Eight characters or more.
export default function AccountPage() {
  const [me, setMe] = useState<{ email: string | null; signed_in: boolean; has_password: boolean } | null>(null);
  const [current, setCurrent] = useState("");
  const [password, setPassword] = useState("");
  const [again, setAgain] = useState("");
  const [msg, setMsg] = useState("");
  const [error, setError] = useState("");
  useEffect(() => {
    fetch("/api/auth/me").then((r) => r.json()).then(setMe).catch(() => setError("Could not reach the server."));
  }, []);
  async function save() {
    setError("");
    setMsg("");
    if (password.length < 8) return setError("Use at least 8 characters.");
    if (password !== again) return setError("The two passwords are not the same.");
    const r = await fetch("/api/auth/password", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(me?.has_password ? { password, current } : { password }),
    });
    if (!r.ok) {
      const d = (await r.json().catch(() => ({}))) as { detail?: string };
      return setError(r.status === 403 ? "The current password is not right." : d.detail ?? `${r.status}`);
    }
    const next = new URLSearchParams(window.location.search).get("next");
    if (next && next.startsWith("/")) return window.location.replace(next);
    setMe({ ...(me ?? { email: null, signed_in: true }), has_password: true });
    setCurrent("");
    setPassword("");
    setAgain("");
    setMsg("Saved. Next time, sign in with your email and this password.");
  }
  if (me && !me.signed_in) return <section className="eg-card ep-panel" style={{ maxWidth: 520 }}><h1 className="eg-h1">Password</h1><p>Sign in first.</p><a className="eg-btn eg-btn--primary" href="/login?next=/account">Sign in</a></section>;
  return (
    <section className="eg-card ep-panel" style={{ maxWidth: 520 }}>
      <div className="eg-overline">{me?.email ?? ""}</div>
      <h1 className="eg-h1">{me?.has_password ? "Change your password" : "Choose a password"}</h1>
      <form className="ep-form" onSubmit={(e) => { e.preventDefault(); void save(); }}>
        {me?.has_password && (
          <label className="ep-field"><span className="ep-small eg-muted">Current password</span>
            <span className="eg-input"><input type="password" autoComplete="current-password" aria-label="Current password" value={current} onChange={(e) => setCurrent(e.target.value)} /></span></label>
        )}
        <label className="ep-field"><span className="ep-small eg-muted">New password (8 characters or more)</span>
          <span className="eg-input"><input type="password" autoComplete="new-password" aria-label="New password" value={password} onChange={(e) => setPassword(e.target.value)} /></span></label>
        <label className="ep-field"><span className="ep-small eg-muted">New password again</span>
          <span className="eg-input"><input type="password" autoComplete="new-password" aria-label="New password again" value={again} onChange={(e) => setAgain(e.target.value)} /></span></label>
        <div><button className="eg-btn eg-btn--primary" type="submit">Save password</button></div>
      </form>
      {msg && <p>{msg}</p>}
      {error && <p className="ep-error">{error}</p>}
    </section>
  );
}
