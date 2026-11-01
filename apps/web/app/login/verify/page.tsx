"use client";

import { useEffect, useState } from "react";

// The sign-in link lands here: exchange the one-time token for a session cookie, then go on.
export default function VerifyPage() {
  const [msg, setMsg] = useState("Signing you in…");
  useEffect(() => {
    const q = new URLSearchParams(window.location.search);
    const token = q.get("token") ?? "";
    const next = q.get("next") ?? "/plan/intake";
    fetch("/api/auth/verify", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ token }) })
      .then(async (r) => {
        if (!r.ok) throw new Error();
        const me = (await r.json()) as { email: string; role: string; has_password: boolean };
        try {
          if (me.role === "analyst") localStorage.setItem("ergplan-analyst", me.email);
          else localStorage.removeItem("ergplan-analyst");
        } catch {
          /* storage may be unavailable */
        }
        const dest = next.startsWith("/") ? next : "/plan/intake";
        // first sign-in by link: choose a password, then go on
        window.location.replace(me.has_password ? dest : `/account?next=${encodeURIComponent(dest)}`);
      })
      .catch(() => setMsg("This link has expired or was already used. Ask for a new one."));
  }, []);
  return (
    <section className="eg-card ep-panel" style={{ maxWidth: 520 }}>
      <h1 className="eg-h1">Sign in</h1>
      <p>{msg}</p>
      {msg.startsWith("This link") && <a className="eg-btn eg-btn--primary" href="/login">Get a new link</a>}
    </section>
  );
}
