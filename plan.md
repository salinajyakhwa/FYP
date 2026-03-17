# Custom Itinerary Plan

## Current State

The repository already has a basic itinerary editor for vendors, but it stores itinerary data as raw JSON on `TravelPackage.itinerary`. At the same time, the traveler-side package detail and booking confirmation templates expect a richer customization system that does not exist in the backend yet. That mismatch is one of the main reasons the current flow is broken.

Before expanding scope, the feature should be rebuilt around a minimal working custom itinerary flow that both vendors and travelers can actually use end to end.

## MVP Goal

From the vendor side:
- A vendor creates a package.
- A vendor defines itinerary items day by day.
- For each day, the vendor can add one or more travel options such as `flight` or `road`.
- Each option can have its own description and additional cost.

From the traveler side:
- A traveler opens a package.
- For each itinerary day, the traveler chooses one of the available options.
- The system calculates the final total based on the selected options.
- The selected items are saved as a custom itinerary tied to that traveler and package.

## Recommended Scope Boundary

The parent-child dependency feature should be deferred for now.

Example:
- "To go to safari, user must first travel to the city."

That is a valid next step, but it introduces dependency validation and ordering rules. It should be added only after the day-by-day customization flow is stable.

## Proposed Data Model

The itinerary should not continue as JSON if the project needs real customization. Use normalized models instead.

### 1. `PackageDay`

Represents a day in the package itinerary.

Suggested fields:
- `package`
- `day_number`
- `title`
- `description`
- `sort_order`

### 2. `PackageDayOption`

Represents one available choice for a given itinerary day.

Suggested fields:
- `package_day`
- `option_type` with choices like `flight` and `road`
- `title`
- `description`
- `additional_cost`
- `is_required`
- `sort_order`

### 3. `CustomItinerary`

Represents one traveler’s saved customized package.

Suggested fields:
- `user`
- `package`
- `base_price`
- `final_price`
- `status`
- `created_at`

### 4. `CustomItinerarySelection`

Represents the traveler’s selected option for one package day.

Suggested fields:
- `custom_itinerary`
- `package_day`
- `selected_option`
- `selected_price`

## Why This Model

This structure separates:
- package definition by vendors
- package customization by travelers
- final booking/payment values

It also gives a clean path for later features such as:
- dependency chains between itinerary items
- optional add-ons
- package versioning
- auditing exact traveler selections even if vendor edits the package later

## Implementation Phases

## Phase 1: Stabilize Existing Broken Flow

Fix mismatches before building the new feature.

### Objective

Make the current package creation, package detail, and itinerary management flow internally consistent so the codebase has a stable base for the custom itinerary feature.

### Concrete Step 1: Audit Current Broken References

Files to inspect first:
- `main/forms.py`
- `main/views.py`
- `main/templates/main/create_package.html`
- `main/templates/main/package_detail.html`
- `main/templates/main/booking_confirmation.html`
- `main/templates/main/manage_itinerary.html`

What to verify:
- Which template fields are actually backed by form fields.
- Which template variables are actually passed by views.
- Which URLs and POST flows are mismatched.

Immediate known mismatches:
- `create_package.html` references `hotel_info`, but `TravelPackageForm` does not define it.
- `package_detail.html` expects `transportation_options`, `hotels`, `base_places`, and `all_activities`, but `package_detail` does not provide them.
- `booking_confirmation.html` expects `custom_itinerary`, but `booking_confirmation` only passes `booking` and `package`.
- `package_detail.html` posts to `booking_confirmation` with `package.id`, but `booking_confirmation` expects a booking id, not a package id.

Done condition:
- A short issue list exists and every mismatch is either removed or intentionally replaced with a temporary fallback.

#### Audit Result

The following mismatches are confirmed in the current codebase.

##### A. Package Creation Template vs Form

Files:
- `main/forms.py`
- `main/templates/main/create_package.html`

Confirmed issue:
- `TravelPackageForm` exposes only:
  - `name`
  - `description`
  - `location`
  - `travel_type`
  - `image`
  - `price`
  - `start_date`
  - `end_date`
- `create_package.html` also renders `form.hotel_info`, which does not exist.

References:
- `main/forms.py` line 97
- `main/templates/main/create_package.html` lines 35 to 36

Impact:
- The create package page is inconsistent with the form contract and may render an empty or broken field block.

##### B. Package Detail Template vs View Context

Files:
- `main/views.py`
- `main/templates/main/package_detail.html`

Confirmed issue:
- `package_detail` only passes:
  - `package`
  - `reviews`
  - `user_can_review`
  - `review_form`
  - `vehicles`
- `package_detail.html` expects additional variables that are never provided:
  - `transportation_options`
  - `hotels`
  - `base_places`
  - `all_activities`

References:
- `main/views.py` lines 125 to 131
- `main/templates/main/package_detail.html` lines 33, 90, 111, 132, 203

Impact:
- The page is built for a customization system that is not implemented in the backend.
- Large sections of UI are disconnected from real data.

##### C. Booking Confirmation Route Contract Is Wrong

Files:
- `main/templates/main/package_detail.html`
- `main/urls.py`
- `main/views.py`

Confirmed issue:
- The package detail form posts to `booking_confirmation` using `package.id`.
- The URL pattern for `booking_confirmation` expects `booking_id`.
- The view fetches `Booking` by that id.

References:
- `main/templates/main/package_detail.html` line 12
- `main/urls.py` line 56
- `main/views.py` lines 644 to 650

Impact:
- Submitting the current package detail form will send the wrong identifier type to the confirmation route.
- This can resolve to the wrong booking or fail with 404 depending on ids in the database.

##### D. Booking Confirmation Template vs View Context

Files:
- `main/views.py`
- `main/templates/main/booking_confirmation.html`

Confirmed issue:
- `booking_confirmation` passes only `booking` and `package`.
- `booking_confirmation.html` expects a non-existent `custom_itinerary` object with deep relationships:
  - `selected_transportation`
  - `selected_hotel_room`
  - `food_preference`
  - `traveler_type`
  - `itinerary_places`
  - `final_price`

References:
- `main/views.py` lines 647 to 649
- `main/templates/main/booking_confirmation.html` lines 14 to 49

Impact:
- The confirmation template is entirely disconnected from the actual backend contract.
- Even if the route were corrected, the page would still render incorrect or empty data.

##### E. Package Detail Customization Inputs Have No Backend Consumer

Files:
- `main/templates/main/package_detail.html`
- `main/views.py`

Confirmed issue:
- The template contains traveler customization inputs for transportation, vehicle, meal preference, hotel room, places, and activities.
- There is no corresponding POST handler that validates or stores these selections.
- The current booking and payment flow uses only `package_id` and `package.price`.

References:
- `main/templates/main/package_detail.html` lines 12 to 239
- `main/views.py` lines 551 to 631

Impact:
- The UI implies customization, but no data from those inputs is persisted or priced.

##### F. Payment Flow Ignores Any Potential Customization

Files:
- `main/views.py`
- `main/models.py`

Confirmed issue:
- Stripe checkout is created from `package.price` only.
- Successful payment creates `Booking` with `total_price=package.price`.
- There is no model for saving pre-booking custom selections.

References:
- `main/views.py` lines 571 to 588
- `main/views.py` lines 617 to 623
- `main/models.py` lines 57 to 70

Impact:
- The current payment flow cannot support itinerary-dependent pricing.

##### G. Vehicle Data Is Over-Broad for Package Detail

Files:
- `main/views.py`
- `main/models.py`

Confirmed issue:
- `package_detail` loads `Vehicle.objects.all()`.
- `Vehicle` belongs to a `Vendor`, not directly to a package.

References:
- `main/views.py` line 107
- `main/models.py` lines 94 to 99

Impact:
- Travelers may see vehicles unrelated to the package they are viewing.
- This is not a strict crash, but it is a data-contract problem.

##### H. Package Detail Template Contains Markdown Code Fences

Files:
- `main/templates/main/package_detail.html`

Confirmed issue:
- The template file starts with ```` ```html ```` and ends with ```` ``` ````.

References:
- `main/templates/main/package_detail.html` lines 1 and 241

Impact:
- Those fence markers do not belong in a Django template file and should be removed during stabilization.

##### I. Manage Itinerary Is Functional but Only as a Temporary JSON Bridge

Files:
- `main/views.py`
- `main/forms.py`
- `main/models.py`

Confirmed issue:
- Vendor itinerary management currently saves a flat list into `TravelPackage.itinerary` JSON.
- That data shape supports basic display, but not traveler-specific option selection or pricing.

References:
- `main/models.py` line 47
- `main/forms.py` lines 78 to 92
- `main/views.py` lines 455 to 470

Impact:
- This is acceptable only as a short-term bridge until relational itinerary models are introduced.

### Concrete Step 2: Fix Package Creation Screen

Target:
- `main/templates/main/create_package.html`

Tasks:
- Remove template references to fields that do not exist in `TravelPackageForm`.
- Only render supported fields:
  - `name`
  - `description`
  - `location`
  - `travel_type`
  - `image`
  - `price`
  - `start_date`
  - `end_date`
- Show field errors clearly so package creation failures are visible.
- Confirm the form `enctype` remains correct for image upload.

Done condition:
- Vendor can open the package creation page without template errors.
- Vendor can submit the page and create a package successfully.

### Concrete Step 3: Simplify Traveler Package Detail to Match Existing Backend

Target:
- `main/views.py`
- `main/templates/main/package_detail.html`

Tasks:
- Remove or replace unsupported customization UI that depends on missing models.
- Keep the page limited to real data already available in the backend:
  - package name
  - description
  - location
  - travel type
  - price
  - dates
  - reviews
  - current JSON itinerary if present
- If vehicles are shown, ensure they are scoped correctly or temporarily hide them if they are not part of the current traveler flow.
- Replace the broken booking/customization form with a simple temporary action:
  - either a basic "Book Now" flow using current package price
  - or a "Customization coming soon" placeholder if booking is not yet stable enough

Done condition:
- Package detail renders without missing-context errors.
- A traveler can view a package without encountering broken form fields or undefined variables.

### Concrete Step 4: Repair Booking Confirmation Contract

Target:
- `main/views.py`
- `main/templates/main/booking_confirmation.html`
- `main/urls.py`

Tasks:
- Decide what `booking_confirmation` means in the temporary pre-custom-itinerary flow.
- Align the route contract so the view parameter matches what the template/form sends.
- If the page is meant to confirm an existing booking:
  - it should accept `booking_id`
  - it should display `booking` and `package`
  - it should not reference `custom_itinerary`
- If the page is not needed yet, remove links to it until the custom itinerary flow is implemented.

Done condition:
- No page uses fake `custom_itinerary` data.
- Any confirmation page that remains is backed by real models and valid route parameters.

### Concrete Step 5: Stabilize Vendor Itinerary Editing as a Temporary Bridge

Target:
- `main/views.py`
- `main/forms.py`
- `main/templates/main/manage_itinerary.html`

Tasks:
- Keep the existing JSON-based itinerary editor only as a temporary bridge.
- Verify the formset renders and submits correctly.
- Ensure delete behavior works for empty and removed rows.
- Ensure submitted itinerary entries are normalized before save:
  - day number present
  - title present
  - activity type present
  - description present
- Sort saved itinerary items by day number so display is predictable.
- Ensure the vendor can only edit their own packages.

Done condition:
- Vendor can add, edit, and save a simple day-by-day itinerary on a package.
- Saved itinerary can be rendered safely on the traveler package page.

### Concrete Step 6: Add Minimal Display of Saved Itinerary on Traveler Side

Target:
- `main/views.py`
- `main/templates/main/package_detail.html`

Tasks:
- Read `package.itinerary` if it is a list.
- Render each saved itinerary item in order.
- Show only fields that are actually stored:
  - day
  - title
  - activity type
  - description
  - inclusions
- Handle empty itinerary gracefully.

Done condition:
- A vendor-created itinerary is visible to travelers even before the full custom option system exists.

### Concrete Step 7: Smoke Test the Stabilized Flow

Manual test path:
1. Create a vendor user.
2. Create a package.
3. Open itinerary management and save 2 to 3 itinerary days.
4. Open the package detail page as a traveler.
5. Confirm page loads and itinerary appears.
6. Confirm no template errors occur in create, detail, or itinerary pages.

Optional code-level validation:
- Add at least one test for package creation page load.
- Add at least one test for package detail page load.
- Add at least one test for itinerary JSON save behavior.

### Phase 1 Exit Criteria

Phase 1 is complete only when:
- package creation works from UI to database
- package detail renders using only real backend data
- booking/confirmation routes no longer rely on fake custom itinerary objects
- vendor itinerary JSON editor works as a temporary bridge
- traveler can view saved itinerary content without broken templates

## Phase 2: Introduce Real Itinerary Models

Tasks:
- Add `PackageDay`.
- Add `PackageDayOption`.
- Add `CustomItinerary`.
- Add `CustomItinerarySelection`.
- Create and run migrations.
- Keep the existing `TravelPackage` model for package-level information such as base price, date range, and vendor ownership.

Expected result:
- Itinerary structure becomes relational and queryable.

## Phase 3: Vendor Itinerary Management

Build a vendor-facing management flow that supports day-by-day options.

Tasks:
- Replace the current JSON itinerary save logic in `manage_itinerary`.
- Allow vendors to add:
  - day number
  - day title
  - day description
  - one or more travel options per day
  - option cost difference
- Support editing and deleting day options.

Expected result:
- Vendors can fully define customizable itinerary choices.

## Phase 4: Traveler Customization Flow

Build the user-facing package customization page.

Tasks:
- Show all package days in order.
- For each day, show available options such as `flight` or `road`.
- Require the traveler to select one option for each required day.
- Show live or server-calculated final price.

Expected result:
- Travelers can create a custom itinerary based on vendor-defined options.

## Phase 5: Persist the Custom Itinerary

Tasks:
- Add a POST endpoint to submit traveler selections.
- Validate that selected options belong to the given package.
- Create a `CustomItinerary`.
- Create one `CustomItinerarySelection` per chosen day option.
- Store final computed price.

Expected result:
- The traveler’s customized plan is saved as real data, not just form state.

## Phase 6: Booking and Payment Integration

The booking system currently books directly against `package_id` and base package price. That is not sufficient once customization changes the cost.

Tasks:
- Update booking confirmation to use `custom_itinerary_id`.
- Update payment flow to charge the custom itinerary final price.
- Store a snapshot of the final price in the booking record.
- Show selected itinerary items on confirmation pages.

Expected result:
- Payment and booking reflect the actual customized package.

## Phase 7: Validation and Testing

Add tests once the core flow is in place.

Minimum tests:
- Vendor can create multiple itinerary days.
- Vendor can create multiple options per day.
- Traveler must choose one option per required day.
- Traveler cannot submit an option belonging to another package.
- Final price is calculated correctly.
- Booking uses custom itinerary final price instead of base package price.

## Deferred Feature: Parent-Child Itinerary Dependencies

After the MVP is stable, dependencies can be added.

Possible direction:
- Add a self-referential dependency field on `PackageDayOption` or on a new itinerary item model.
- Prevent selection of child items unless all parent requirements are satisfied.

Example:
- `Safari` depends on `Travel to Chitwan`.

This should be implemented only after the basic itinerary selection and persistence logic is working.

## Suggested Acceptance Criteria

The custom itinerary MVP is complete when:
- A vendor can create a package and define itinerary days.
- A vendor can add multiple travel options for each day.
- A traveler can choose one option per day.
- The app computes the correct final price.
- The traveler’s selections are stored in the database.
- Booking confirmation displays the selected itinerary items.
- Payment uses the customized total, not only the base package price.

## Practical Recommendation

Do not extend the current JSON itinerary field further. Use it only temporarily if needed during migration, then phase it out. The custom itinerary feature will be significantly easier to maintain if the project moves to explicit relational models now instead of layering more behavior onto JSON.
