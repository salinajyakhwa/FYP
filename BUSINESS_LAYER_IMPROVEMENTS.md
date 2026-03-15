# Business Layer Improvement Plan (Capstone-Ready + AI Integrations + Bandwidth/Scale)

## 1) Current business-layer assessment

The project has strong core features (roles, packages, bookings, reviews, dashboards, payments), but a lot of domain/business logic currently sits directly in `views.py`. That makes the code hard to test, scale, and evolve for advanced capstone outcomes.

Key examples:
- Booking/payment confirmation logic is tightly coupled to web session state (`pending_booking_package_id`) in request handlers.
- Vendor/admin state changes (booking status, vendor status) are done inline and can bypass richer lifecycle rules.
- Payment verification (eSewa) verifies signatures but does not persist a payment-domain event or idempotent booking update.
- Domain constraints (slot inventory consistency, date validity, review/rating bounds, status transitions) are mostly enforced procedurally in views/forms rather than centrally.

---

## 2) High-impact business-layer improvements

## A. Introduce a Service Layer (highest priority)

Create explicit service modules (e.g., `main/services/`) and move domain logic from views into use-case classes/functions.

Suggested service boundaries:
- `booking_service.py`
  - `create_pending_booking(user, package, travelers)`
  - `confirm_booking_after_payment(payment_ref)`
  - `cancel_booking(actor, booking)`
- `payment_service.py`
  - `create_stripe_checkout(...)`
  - `verify_esewa_payload(...)`
  - `record_payment_event(...)`
- `vendor_service.py`
  - `update_booking_status(vendor, booking, new_status)` with transition rules
  - `approve_vendor(admin, vendor)` / `reject_vendor(...)`
- `review_service.py`
  - `submit_verified_review(user, package, form_data)`

Why this matters for capstone quality:
- Gives clean architecture (controllers/views thin; business rules centralized).
- Easier unit testing of domain logic without HTTP request setup.
- Faster feature iteration for AI add-ons.

---

## B. Add domain invariants at model/service level

Implement explicit validation:
- `TravelPackage`: enforce `start_date <= end_date`, non-negative/realistic price and slots.
- `Review`: enforce rating range (1-5) at model level using validators/check constraints.
- `Booking`: enforce legal status transitions (`pending -> confirmed/cancelled`, not arbitrary toggles).

Add DB-level constraints where possible:
- Check constraints for valid numeric ranges.
- Unique constraint to prevent duplicate verified review per `(user, package)` if desired business rule.

---

## C. Make payment and booking flows idempotent + transactional

For reliability and scale:
- Add a dedicated `PaymentTransaction` model with fields like:
  - provider (`stripe`, `esewa`), provider_txn_id, status, amount, currency, payload, booking/user/package refs.
- Wrap booking confirmation updates in `transaction.atomic()`.
- Use idempotency keys (provider transaction UUID/session ID) so repeated callbacks do not create duplicate bookings.
- Persist every payment callback attempt for audit/debugging.

---

## D. Move long-running work to async jobs

Use Celery + Redis (or Django Q/RQ) for:
- email verification sends, reminders, post-booking notifications
- AI inference tasks (recommendations/summaries)
- analytics aggregation and periodic materialization

Business value:
- Faster user response times
- Better throughput under load (“bandwidth increase”)
- More robust retry/error handling

---

## E. Add observability and business metrics

Track business KPIs and service health:
- conversion funnel (`package_view -> checkout -> paid -> booked`)
- booking confirmation latency
- payment callback failure rate
- cancellation reasons
- vendor approval turnaround time

Implement structured logging + Sentry/OpenTelemetry for production-grade troubleshooting.

---

## 3) AI integration roadmap (capstone differentiator)

## Phase 1 (quick win)
1. **AI package recommendation ranking**
   - Inputs: user profile, booking history, location preferences, seasonality.
   - Output: re-ranked package list with explainability tags.

2. **AI itinerary quality assistant for vendors**
   - Suggest day plans, pacing, inclusions, and missing essentials.
   - Safety: human-in-the-loop approval before publish.

3. **Review summarization + sentiment scoring**
   - Generate “what travelers like/dislike” snapshots for each package.

## Phase 2 (strong capstone depth)
4. **Dynamic pricing advisor (decision support, not auto-apply initially)**
   - Recommend price ranges based on demand, occupancy, season, competitor bands.

5. **Demand forecasting and slot optimization**
   - Forecast expected bookings by package/time window.
   - Suggest capacity changes and marketing triggers.

6. **Fraud/risk signals for payments/bookings**
   - Rule-based first, then ML-assisted anomaly scoring.

Implementation guidance:
- Build AI features behind service interfaces (`recommendation_service`, `ai_itinerary_service`) so you can swap providers/models.
- Store prompt + model metadata + outputs for reproducibility and capstone evaluation.
- Add feature flags for safe rollout.

---

## 4) Bandwidth and scalability plan

## Application layer
- Cache heavy reads (package list filters, dashboard aggregates) using Redis cache.
- Add pagination consistently on all large lists (bookings, reviews, admin/vendor panels).
- Optimize ORM usage (`select_related`, `prefetch_related`) and avoid N+1 queries.

## Database layer
- Add indexes on frequently filtered fields:
  - booking status/date/package/vendor
  - package location/type/date ranges
  - review package/date/rating
- Use periodic aggregate tables/materialized views for dashboards.

## Delivery layer
- Use CDN/object storage for media (package images/profile pics).
- Add API endpoints (DRF) for future mobile/SPA clients and AI microservice access.

---

## 5) Testing strategy to strengthen the business layer

Target test pyramid:
- **Unit tests** (services): status transitions, payment idempotency, slot calculations.
- **Integration tests**: payment callback -> transaction record -> booking confirmation.
- **Contract tests**: external provider payload validation (Stripe/eSewa).
- **Load tests**: package search/list, checkout, dashboard queries.

Minimum acceptance criteria for “solid capstone”:
- >80% coverage for service layer modules.
- Zero duplicate bookings for repeated payment callbacks.
- Deterministic business-rule behavior (documented transition matrix).

---

## 6) Suggested 6-week execution order

1. Week 1: create service layer + refactor booking/payment use-cases.
2. Week 2: payment transaction model + idempotency + atomic workflows.
3. Week 3: add constraints/indexes + service unit tests.
4. Week 4: async job queue + observability stack.
5. Week 5: AI recommender + review summarization MVP.
6. Week 6: benchmarking, load tests, capstone report with before/after metrics.

---

## 7) Deliverables that impress capstone evaluators

- Architecture diagram (presentation + sequence diagram for payment/booking).
- Measured performance gains (latency, throughput, failure rate reductions).
- AI model cards, prompt/version tracking, and bias/safety considerations.
- Production-readiness checklist (monitoring, retries, backups, incident handling).

This plan will move the project from a feature-rich prototype to a robust, scalable, and AI-augmented capstone system.
