# Launch checklist: what is NOT done

The app runs end to end, locally. Below is what stands between this and real users.
Ordered by how badly it would hurt.

## Blockers

- [ ] **Weather licence.** Open-Meteo's free API is for non-commercial use. A commercial
      product needs their paid plan (or another provider). The code only needs new URLs.
- [ ] **Real affiliate accounts.** None configured: every click today earns nothing.
      Apply to Amazon Associates, Awin (outdoor merchants), maybe Impact/CJ/AvantLink.
- [ ] **Real product data.** The 169 seed products have indicative prices and approximate
      specs and no images. Connect at least one real feed per market.
- [ ] **Rental partners** are placeholders (example.com). No deals exist.
- [ ] **Legal pages** (privacy, terms, affiliate disclosure) are drafts, not reviewed by
      a lawyer. Cookie banner not needed today (one essential cookie, no trackers) but
      must be revisited if you add analytics.
- [x] **Name.** Thruwear, tagline "Wear it thru." (`BRAND_NAME`, `BRAND_TAGLINE`).
- [ ] **Domain and trademark.** thruwear.com was unregistered on 2026-10-24: buy it, set
      `BRAND_DOMAIN`, and run a trademark search (EUIPO/USPTO) before launch.
- [ ] **Design.** `THEME` and `frontend/src/theme/tokens.css` are where it changes.
- [ ] **Images from the design concepts** (photos from another brand's site) are internal
      placeholders and must never ship. They are not in this repo and `.gitignore`
      blocks the folder.

## Needed soon after

- [ ] **Email sending (password reset and sign-in links).** Built; needs a mail provider.
  Set `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `MAIL_FROM` (Brevo, Mailgun,
  Amazon SES...: free tiers cover a launch) and set up SPF/DKIM on the domain so the links
  don't land in spam. Without SMTP the links only work on a local machine (shown on screen).
- [ ] **Clean up idle guests.** Run `python -m app.cli prune-guests --days 30` daily (cron).
- [ ] **Email verification** on sign-up.
- [ ] **Hosting.** Docker image is ready; choose a host, set `ENVIRONMENT=production`,
      a real `SECRET_KEY`, `COOKIE_SECURE=true`, HTTPS, Postgres backups.
- [ ] **AI in production.** The local model runs on your PC. A public site needs it on a
      server or a hosted OpenAI-compatible provider (see docs/AI_SETUP.md).
- [ ] **Rate limiting** is in memory, per process. Fine for one server; use Redis or the
      proxy's limiter if you scale out.
- [ ] **Commission reconciliation.** Clicks are logged with a sub-id, but network reports
      are not imported, so revenue per trip can't be measured in the app yet.
- [ ] **Scheduled feed refresh** (cron). Manual import only today.
- [ ] **Monitoring** (errors, uptime) and **analytics** (privacy-friendly).
- [x] **CI**: GitHub Actions runs pytest, vitest, the frontend build and the Docker build.
- [ ] **End-to-end browser tests** in CI. Flows were checked manually with Playwright.

## Product risks

- [ ] **The warmth model is unvalidated.** Numbers are reasonable on test trips, but no
      real traveller has confirmed them. Add a post-trip "were you warm enough?" survey.
- [ ] **Classifier on real feeds.** Tested on sample rows, not on a full merchant feed.
      Expect misclassified products in the first imports: check the admin skip/error list.
- [ ] **Geocoding** uses Open-Meteo plus a 79-place offline list. Small villages may be
      missing or ambiguous; the user can always pick a place by hand.
- [ ] **Accessibility** has basic semantics and keyboard support, not an audit.
- [ ] **Languages.** UI is English only. The trip parser reads English and Italian.
