import { Link } from "react-router-dom";
import { ItineraryCards } from "../components/ItineraryCards";

export default function Ideas() {
  return (
    <main className="page">
      <div className="wrap">
        <div className="page-head">
          <div>
            <p className="kicker">Looking for ideas</p>
            <h1>Ready-made trips, day by day</h1>
            <p className="lede" style={{ marginTop: 12, maxWidth: "62ch" }}>
              Built from the places that thousands of organised trips visit most, with what is worth it and what to
              skip at every stop. Like one? We pack your bag for it.
            </p>
          </div>
          <Link className="btn" to="/trips/new">I already have a trip</Link>
        </div>
        <ItineraryCards />
      </div>
    </main>
  );
}
