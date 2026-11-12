# Flights: what works today and what turns each part on

The trip page has a **Flights** section: every flight leg of the trip, and for each leg every
flight of its day in time order, with "day before / day after", direct-only, by time or by
price, and checks between the picks (a flight on another day than the plan, a next-day
arrival, less than 3 hours between two separate tickets). The board shows the picked flight
on the leg ("AEP–FTE 08:45"), and "I booked it" locks that day.

| Part | Needs | Without it |
|---|---|---|
| Links per leg (Google Flights, Skyscanner, Aviasales, the country's own airlines) and "All legs on Kayak" | nothing | — |
| Recent prices in the leg editor | `TRAVELPAYOUTS_TOKEN` (+ `TRAVELPAYOUTS_MARKER` for commission) | no prices line |
| Every flight of the day, one-ticket price | `DUFFEL_ACCESS_TOKEN` (test or live) | the section shows links only |
| Booking inside the app | a **test** Duffel token today | button hidden |

## 1. Travelpayouts (free, 10 minutes)

1. Sign up at travelpayouts.com, join the **Aviasales** program.
2. Profile → API token: copy it into `TRAVELPAYOUTS_TOKEN`. Your partner ID goes in
   `TRAVELPAYOUTS_MARKER` (it is also added to the Aviasales links, so bookings earn).
3. The prices are what other travellers saw in the last days (cached), not live seats. The app
   says so next to them.

## 2. Duffel, test mode (free, 10 minutes)

1. Sign up at duffel.com. Developers → Access tokens → create a **test** token
   (`duffel_test_...`). Put it in `DUFFEL_ACCESS_TOKEN` and restart.
2. Test mode searches Duffel's test airlines ("Duffel Airways") plus test copies of real
   routes; bookings are fake and cost nothing. Use it to try the whole flow.

## 3. Duffel live: real search, then real booking

**Real search** works as soon as you put a live token (`duffel_live_...`). No ticket is bought, but check Duffel's pricing page: it may charge when searches far outnumber bookings.
Check which airlines cover your routes: in Argentina and Chile the low-cost airlines
(JetSMART, Flybondi) and LATAM are the ones that matter; Aerolíneas Argentinas has no public
API and may be missing. The links stay on every leg for that reason.

**Real booking** is switched off in the code (`app/travel/duffel.py`, `book()`): with a live
token Duffel takes the money from *your* Duffel balance, and nothing takes it from the
traveller. Before turning it on you need:

- [ ] A company (Duffel signs live accounts with a business, not a person) and Duffel's live
      account approval.
- [ ] **Duffel Payments** (the traveller pays by card, Duffel handles the card data): a
      payment step in the app before the order.
- [ ] Terms of sale for tickets (you become the seller of record or an agent of the
      airline), change and refund handling, and the airlines' fare rules shown before paying.
- [ ] Customer service: schedule changes and cancellations arrive by webhook and must reach
      the traveller.
- [ ] Pricing: Duffel charges per order; decide whether to add a fee (the app is free for
      travellers, so the margin is the only revenue here).

Until then the honest flow is: find the flight here, book on the airline or the search
site from the links, press "I booked it elsewhere".

## Data

`backend/app/travel/airports.json`: OurAirports, public domain, airports with scheduled
service. Rebuild with `python tools/travel/build_airports.py`.
