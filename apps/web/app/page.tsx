import Link from "next/link";

export default function Home() {
  return (
    <>
      <h1 className="eg-h1">
        What does your power <em>really</em> cost?
      </h1>
      <section className="eg-glass" style={{ padding: "var(--space-6)" }}>
        <div className="eg-card__head">
          <div>
            <h2 className="eg-card__title">How ergPLAN works</h2>
            <p className="eg-card__sub">Drop a bill. Every number that comes back names its regulation and page.</p>
          </div>
        </div>
        <ol style={{ margin: 0, paddingLeft: 20, lineHeight: "28px" }}>
          <li>Drop your electricity bills, or tell us your state, voltage and monthly bill.</li>
          <li>See today&apos;s cost rebuilt from your DISCOM&apos;s tariff order, line by line.</li>
          <li>See the landed cost of rooftop, open-access solar and wind, storage and IEX at your meter.</li>
          <li>Describe your site; we build a 15-minute load profile from your bills.</li>
          <li>Optimise the mix under your state&apos;s banking and settlement rules.</li>
          <li>Take away a live plan you can question by voice.</li>
        </ol>
        <div className="ep-row" style={{ marginTop: "var(--space-6)" }}>
          <Link className="eg-btn eg-btn--ghost" href="/documents">
            Browse the regulation library
          </Link>
        </div>
      </section>
    </>
  );
}
