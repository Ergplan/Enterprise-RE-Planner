import Link from "next/link";

export default function NotFound() {
  return (
    <section className="eg-card">
      <h2 className="eg-card__title">Not built yet, or not found</h2>
      <p className="eg-card__sub">This part of ergPLAN arrives in a later stage, or the link is wrong.</p>
      <p><Link className="eg-btn eg-btn--ghost" href="/">Go to the start</Link></p>
    </section>
  );
}
