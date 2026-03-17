# Custom Itinerary Feature Documentation

## Overview

The custom itinerary feature allows a vendor to define package days and day-specific travel choices, and allows a traveler to build and save a package variant by selecting one option for each required day.

This feature now covers:
- vendor-side itinerary day management
- vendor-side per-day option management
- traveler-side custom option selection
- saved custom itinerary records
- payment method chooser
- Stripe checkout for base packages and saved custom itineraries
- eSewa handoff flow for base packages and saved custom itineraries
- booking creation linked to the saved custom itinerary

The current implementation keeps the old `TravelPackage.itinerary` JSON field as a compatibility bridge, but the primary source of truth is now relational.

## Core Models

### `TravelPackage`

This remains the package-level parent model.

Important fields:
- `vendor`
- `name`
- `description`
- `location`
- `travel_type`
- `price`
- `start_date`
- `end_date`
- `itinerary`

Notes:
- `itinerary` is still present as JSON for compatibility and fallback display.
- New feature work should prefer relational itinerary models.

### `PackageDay`

Represents one day in the package plan.

Fields:
- `package`
- `day_number`
- `title`
- `description`
- `sort_order`

Purpose:
- defines the traveler-visible day structure
- groups the selectable options for that day

### `PackageDayOption`

Represents one selectable option within a package day.

Fields:
- `package_day`
- `option_type`
- `title`
- `description`
- `additional_cost`
- `is_required`
- `sort_order`

Examples:
- Day 1:
  - `Flight to Pokhara`, `additional_cost=120`
  - `Road transfer to Pokhara`, `additional_cost=20`

### `CustomItinerary`

Represents one traveler’s saved customized package.

Fields:
- `user`
- `package`
- `base_price`
- `final_price`
- `status`
- `created_at`
- `updated_at`

Current statuses:
- `draft`
- `submitted`
- `confirmed`
- `cancelled`

### `CustomItinerarySelection`

Represents the selected option for one day within a saved custom itinerary.

Fields:
- `custom_itinerary`
- `package_day`
- `selected_option`
- `selected_price`

### `Booking`

The booking model now supports a link to the saved custom itinerary that was actually paid for.

Additional field:
- `custom_itinerary`

Purpose:
- allows the booking to reference the exact saved customized package
- keeps payment and booking aligned with traveler selections

## Feature Flow

## 1. Vendor Flow

### Package Creation

Vendor creates a package through:
- `vendor/package/create/`

This stores the base package information only.

### Itinerary Management

Vendor manages itinerary through:
- `vendor/package/<package_id>/manage-itinerary/`

The page supports:
- adding itinerary days
- editing itinerary days
- deleting itinerary days
- adding options per day
- editing options
- deleting options

### Vendor Data Rules

Current validation rules:
- `day_number` must be unique within a package
- option must belong to a day in the same package
- text fields are trimmed before save
- package day ordering uses `day_number`, then `sort_order`
- option ordering uses `sort_order`

### JSON Compatibility Sync

Whenever relational itinerary data changes, the app synchronizes `TravelPackage.itinerary`.

This exists only as a temporary bridge for:
- compatibility with older views or data
- fallback rendering when relational data is absent

New logic should treat relational records as the primary source.

## 2. Traveler Flow

### Package Detail

Traveler opens:
- `package/<package_id>/`

If the package has relational itinerary days, the page renders:
- each package day in order
- all options for that day
- one radio-style selection group per day

If there are no relational itinerary days, the page falls back to the JSON itinerary display.

### Selection Rules

Traveler must select one option for each required day group.

Current implementation:
- builds the form dynamically from `PackageDay` and `PackageDayOption`
- validates that submitted option ids belong to the correct package day
- computes the price server-side

### Preview

Traveler can click:
- `Preview Custom Total`

This performs:
- form validation
- selected option summary generation
- `customization_extra_cost` calculation
- `customization_total` calculation

Formula:
- `customization_total = package.price + sum(selected_option.additional_cost)`

### Save Custom Itinerary

Traveler can click:
- `Save Custom Itinerary`

This performs:
- validation of selections
- creation of a `CustomItinerary`
- creation of one `CustomItinerarySelection` row per selected day
- redirect to the saved custom itinerary page

## 3. Saved Custom Itinerary

Saved custom itinerary detail page:
- `custom-itinerary/<custom_itinerary_id>/`

This page shows:
- package name
- vendor
- base price
- final price
- status
- selected option per day

Access control:
- only the owner can view their saved custom itinerary

## Payment Flow

## 1. Payment Chooser

Both standard package booking and custom itinerary booking now pass through a chooser page.

Routes:
- `payment/choose/<package_id>/`
- `payment/choose/custom-itinerary/<custom_itinerary_id>/`

The chooser displays:
- target package name
- total amount
- `Pay with Stripe`
- `Pay with eSewa`

## 2. Stripe Flow

### Base Package Stripe Checkout

Route:
- `create-checkout-session/<package_id>/`

Behavior:
- creates a Stripe checkout session using `package.price`
- stores pending package payment data in session
- redirects to Stripe

### Custom Itinerary Stripe Checkout

Route:
- `create-checkout-session/custom-itinerary/<custom_itinerary_id>/`

Behavior:
- creates a Stripe checkout session using `custom_itinerary.final_price`
- stores pending custom itinerary payment data in session
- redirects to Stripe

### Stripe Success

Route:
- `payment-success/`

Behavior:
- reads the pending payment target from session
- creates or updates the final booking
- marks custom itinerary as `confirmed` when applicable
- clears pending payment session keys

## 3. eSewa Flow

### Base Package eSewa Checkout

Route:
- `payment/esewa-checkout/<package_id>/`

### Custom Itinerary eSewa Checkout

Route:
- `payment/esewa-checkout/custom-itinerary/<custom_itinerary_id>/`

Behavior:
- creates the signed eSewa payload
- stores pending payment target and transaction uuid in session
- renders a handoff page that auto-submits to the eSewa portal

Important note:
- this is not a pure HTTP redirect
- eSewa requires a signed `POST`
- therefore the app uses an auto-submitting HTML form

### eSewa Verify

Route:
- `payment/esewa-verify/`

Behavior:
- accepts the `data` payload returned by eSewa
- decodes the Base64 response
- verifies the response signature
- checks transaction uuid against the pending session value
- confirms payment status is `COMPLETE`
- creates or updates the corresponding booking
- redirects to booking confirmation

## Booking Flow

### Booking Creation Logic

There are now two booking paths:

### Base Package Booking

Booking is created using:
- `package`
- `total_price = package.price`
- `custom_itinerary = null`

### Custom Itinerary Booking

Booking is created or updated using:
- `package = custom_itinerary.package`
- `custom_itinerary = saved custom itinerary`
- `total_price = custom_itinerary.final_price`

This ensures that bookings reflect the actual customized package the user paid for.

### Booking Confirmation

Route:
- `booking/confirmation/<booking_id>/`

Behavior:
- shows standard booking details
- if booking has `custom_itinerary`, it also shows the selected itinerary items

## Session Keys Used in Payment

The payment flow currently uses session keys to track pending payment context.

Keys:
- `pending_booking_package_id`
- `pending_custom_itinerary_id`
- `pending_payment_provider`
- `pending_payment_transaction_uuid`

These are used to:
- preserve payment target between redirect steps
- match payment completion back to the correct package or saved custom itinerary
- validate eSewa callback transaction context

## Templates Involved

Main traveler templates:
- `main/templates/main/package_detail.html`
- `main/templates/main/custom_itinerary_detail.html`
- `main/templates/main/choose_payment.html`
- `main/templates/main/esewa_checkout.html`
- `main/templates/main/payment_success.html`
- `main/templates/main/booking_confirmation.html`
- `main/templates/main/my_bookings.html`

Vendor template:
- `main/templates/main/manage_itinerary.html`

## Main Views Involved

Primary views:
- `package_detail`
- `custom_itinerary_detail`
- `manage_itinerary`
- `choose_payment`
- `choose_custom_itinerary_payment`
- `create_checkout_session`
- `create_custom_itinerary_checkout_session`
- `esewa_checkout`
- `esewa_custom_itinerary_checkout`
- `esewa_verify`
- `payment_success`
- `booking_confirmation`

## Current Limitations

The feature is working, but there are still limits and follow-up work.

### 1. JSON Compatibility Layer Still Exists

The project still writes itinerary data to `TravelPackage.itinerary`.

This should eventually be removed once all reads are fully relational.

### 2. Payment Identity Is Session-Based

The current payment resolution depends on session state.

This is acceptable for the current project stage, but a more robust version would also persist:
- payment attempts
- transaction ids
- provider responses
- audit metadata

### 3. No Parent-Child Dependency Logic Yet

The planned dependency rule system is still deferred.

Example future rule:
- user cannot select safari until a city-travel prerequisite is satisfied

### 4. No Advanced Pricing Rules Yet

Current pricing is:
- base package price
- plus sum of selected option additional costs

There is no support yet for:
- traveler count multipliers
- seasonal pricing
- tax rules by provider
- coupon logic

## Recommended Next Improvements

Suggested next steps:
- add a dedicated payment transaction model
- persist provider reference ids and raw callback payloads
- remove old JSON itinerary dependency
- add tests for chooser, Stripe, and eSewa flows
- add tests for custom itinerary booking creation
- add dependency logic between itinerary items
- add traveler count support to pricing

## Quick Test Checklist

### Vendor

1. Create package.
2. Add itinerary days.
3. Add multiple options per day.
4. Confirm day and option ordering.

### Traveler

1. Open package detail.
2. Select one option per required day.
3. Preview total.
4. Save custom itinerary.
5. Open saved custom itinerary page.

### Payment

1. Click `Proceed to Payment`.
2. Confirm chooser page appears.
3. Choose Stripe and verify standard flow.
4. Choose eSewa and verify handoff to eSewa portal.
5. On success, confirm booking is created.
6. Confirm booking detail shows custom selections when relevant.
