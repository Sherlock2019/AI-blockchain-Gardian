import { Link } from "react-router-dom";
import { BusinessValue, PITCH, StoryStrip } from "../components/Story";

const CARDS = [
  {
    number: "1",
    title: "The problem",
    text: "Enterprise workflows require humans to search across documents, systems and policies before making decisions.",
  },
  {
    number: "2",
    title: "The AI solution",
    text: "AI agents gather evidence, retrieve knowledge, identify anomalies and prepare recommendations.",
  },
  {
    number: "3",
    title: "The trust layer",
    text: "Deterministic policies control authority, humans approve high-risk actions, and blockchain provides verifiable evidence.",
  },
];

export function LandingPage() {
  return (
    <div className="landing">
      <section className="hero">
        <h1>TrustChain AI</h1>
        <p className="hero-tagline">Human-Governed, Web3-Verifiable AI Agents</p>
        <p className="hero-sub">
          Let AI do the investigation.
          <br />
          Keep humans in control of consequential decisions.
        </p>
        <Link className="cta" to="/demo">
          Run the 5-minute demo
        </Link>
        <p className="pitch">{PITCH}</p>
      </section>

      <div className="landing-cards">
        {CARDS.map((card) => (
          <div key={card.title} className="landing-card">
            <span className="landing-number">{card.number}</span>
            <h2>{card.title}</h2>
            <p>{card.text}</p>
          </div>
        ))}
      </div>

      <section className="band">
        <h2 className="band-title">The complete story</h2>
        <StoryStrip />
      </section>
      <BusinessValue />
      <p className="muted center">
        A proof of concept. Synthetic data, mock payments and a local development blockchain. No real money
        moves.
      </p>
    </div>
  );
}
