import { Link } from "react-router-dom";
import { HomeGlobe } from "../components/Maps";
import { brandName, useApp } from "../lib/app-context";
import { OwnTripForm } from "./Start";

/** Home (design H21): the drawn globe, one sentence, one box. Phone: globe on top.
 *  Computer: globe on the left, the words on the right. */
export default function Landing() {
  const { config } = useApp();
  const name = brandName(config);

  return (
    <main className="home">
      <div className="home-globe"><HomeGlobe /></div>
      <section className="home-side">
        <h1 className="home-h">Pick a place.<br /><span>We pack the bag.</span></h1>
        <OwnTripForm compact />
        <div className="home-links">
          <Link to="/ideas" className="home-ideas">No idea yet? <b>Get ideas →</b></Link>
          <Link to="/trips" className="home-ideas">My trips →</Link>
        </div>
        <p className="home-note">{name} is free. A shop link may earn us a commission; it never picks your clothes.</p>
      </section>
    </main>
  );
}
