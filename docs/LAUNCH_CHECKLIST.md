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
- [ ] **Brand, name, domain, design.** Placeholders. `BRAND_NAME`, `THEME` and
      `frontend/src/theme/tokens.css` are where they change.
- [ ] **Images from the design concepts** (photos from another brand's site) are internal
      placeholders and must never ship. They are not in this repo and `.gitignore`
      blocks the folder.

## Needed soon after

- [ ] **Password reset by email.** Not built: there is no email sending at all.
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
