import { Link, useParams } from "react-router-dom";
import { brandName, useApp } from "../lib/app-context";
import NotFound from "./NotFound";

export default function Legal() {
  const { page } = useParams();
  const { config } = useApp();
  const name = brandName(config);
  const email = config?.brand.support_email ?? "support@example.com";

  const draft = (
    <div className="banner warn" style={{ marginBottom: 24 }}>
      Draft. This page has not been reviewed by a lawyer and must be before public launch.
    </div>
  );

  if (page === "affiliate") return (
    <main className="page"><div className="wrap prose" style={{ maxWidth: 760 }}>
      <p className="kicker">Legal</p><h1>Affiliate disclosure</h1>{draft}
      <p>{name} is free to use and always will be. We pay for it with affiliate commissions: when you click a shop link and buy,
        the shop may pay us a small percentage. You pay the same price.</p>
      <p>Commissions never decide what we recommend. Rankings come from fit to your trip (stars) and price. If something you
        already own does the job, we tell you not to buy anything.</p>
      <p>Rental links go to partner rental shops, which may also pay us a commission.</p>
      <p>As an Amazon Associate we may earn from qualifying purchases.</p>
    </div></main>
  );
  if (page === "privacy") return (
    <main className="page"><div className="wrap prose" style={{ maxWidth: 760 }}>
      <p className="kicker">Legal</p><h1>Privacy</h1>{draft}
      <h2>What we store</h2>
      <ul>
        <li>Account: email, a hashed password, optional name, fit preferences.</li>
        <li>Your trips (places, dates, activities) and your wardrobe.</li>
        <li>Shop link clicks: which product, when, and a one-way hash of your browser type. No IP addresses are stored.</li>
      </ul>
      <h2>What we don't do</h2>
      <ul>
        <li>We don't sell your data. We don't use advertising trackers.</li>
        <li>AI features run on a model we host ourselves; your trip text is not sent to third-party AI companies.</li>
      </ul>
      <h2>Third parties</h2>
      <p>Weather comes from Open-Meteo (we send coordinates, never your identity). Shops you click through to have their own policies.</p>
      <h2>Your rights</h2>
      <p>You can download or delete everything from your <Link to="/account">account page</Link>. Questions: {email}.</p>
      <h2>Cookies</h2>
      <p>One essential cookie keeps you signed in. Your theme choice is kept in your browser.</p>
    </div></main>
  );
  if (page === "terms") return (
    <main className="page"><div className="wrap prose" style={{ maxWidth: 760 }}>
      <p className="kicker">Legal</p><h1>Terms of use</h1>{draft}
      <p>{name} gives clothing suggestions based on estimates of weather and of how warm clothes are. They are not safety advice.
        In the mountains, check local conditions, and ask a guide or a mountain hut when in doubt.</p>
      <p>Prices and availability come from shops and can change; the shop's page is what counts. We don't sell anything ourselves:
        purchases and rentals are contracts between you and the shop.</p>
      <p>Don't misuse the service (scraping, automated account creation, attacks). We may suspend accounts that do.</p>
    </div></main>
  );
  return <NotFound />;
}
