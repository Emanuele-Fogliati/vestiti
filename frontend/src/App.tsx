import { Route, Routes } from "react-router-dom";
import { Layout } from "./components/Layout";
import Account from "./pages/Account";
import Admin from "./pages/Admin";
import Auth from "./pages/Auth";
import HowItWorks from "./pages/HowItWorks";
import Landing from "./pages/Landing";
import Legal from "./pages/Legal";
import NewTrip from "./pages/NewTrip";
import NotFound from "./pages/NotFound";
import TripPage from "./pages/TripPage";
import Trips from "./pages/Trips";
import Wardrobe from "./pages/Wardrobe";

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Landing />} />
        <Route path="trips" element={<Trips />} />
        <Route path="trips/new" element={<NewTrip />} />
        <Route path="trips/:id" element={<TripPage />} />
        <Route path="wardrobe" element={<Wardrobe />} />
        <Route path="account" element={<Account />} />
        <Route path="admin" element={<Admin />} />
        <Route path="login" element={<Auth mode="login" />} />
        <Route path="register" element={<Auth mode="register" />} />
        <Route path="how-it-works" element={<HowItWorks />} />
        <Route path="legal/:page" element={<Legal />} />
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  );
}
