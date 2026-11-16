import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import { Layout } from "./components/Layout";
import Account from "./pages/Account";
import Admin from "./pages/Admin";
import Auth, { EmailLinkLanding, ForgotPassword, ResetPassword } from "./pages/Auth";
import HowItWorks from "./pages/HowItWorks";
import ItineraryPage from "./pages/ItineraryPage";
import Landing from "./pages/Landing";
import Preview from "./pages/Preview";
import Legal from "./pages/Legal";
import NewTrip from "./pages/NewTrip";
import NotFound from "./pages/NotFound";
import TripPage from "./pages/TripPage";
import Trips from "./pages/Trips";
import Wardrobe from "./pages/Wardrobe";
import TrailPage from "./pages/TrailPage";
import Trails from "./pages/Trails";

export default function App() {
  return (
    <Routes>
      <Route path="preview" element={<Preview />} />
      <Route path="phone" element={<Preview only="phone" />} />
      <Route element={<Layout />}>
        <Route index element={<Landing />} />
        {/* old doors (Manu 2026-11-16: one Trips page): a new trip, or the recommended ones */}
        <Route path="start" element={<ToNew />} />
        <Route path="ideas" element={<Navigate to="/trips?tab=recommended" replace />} />
        <Route path="ideas/:slug" element={<ItineraryPage />} />
        <Route path="trips" element={<Trips />} />
        <Route path="trips/new" element={<NewTrip />} />
        <Route path="trips/:id" element={<TripPage />} />
        <Route path="wardrobe" element={<Wardrobe />} />
        <Route path="trails" element={<Trails />} />
        <Route path="trails/:id" element={<TrailPage />} />
        <Route path="account" element={<Account />} />
        <Route path="admin" element={<Admin />} />
        <Route path="login" element={<Auth mode="login" />} />
        <Route path="register" element={<Auth mode="register" />} />
        <Route path="forgot-password" element={<ForgotPassword />} />
        <Route path="reset-password" element={<ResetPassword />} />
        <Route path="sign-in-link" element={<EmailLinkLanding />} />
        <Route path="how-it-works" element={<HowItWorks />} />
        <Route path="legal/:page" element={<Legal />} />
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  );
}

/** /start?q=Lima still works: it opens a new trip and looks the place up. */
function ToNew() {
  const loc = useLocation();
  return <Navigate to={`/trips/new${loc.search}`} replace />;
}
