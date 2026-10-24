import { Link } from "react-router-dom";

export default function NotFound() {
  return (
    <main className="page">
      <div className="wrap" style={{ maxWidth: 560 }}>
        <p className="kicker">404</p>
        <h1 style={{ fontSize: 40, marginBottom: 16 }}>Wrong trail</h1>
        <p className="muted" style={{ marginBottom: 20 }}>This page doesn't exist.</p>
        <Link className="btn primary" to="/">Back to start</Link>
      </div>
    </main>
  );
}
