# Mobile app screenshots

The real app code, rendered at phone size (390 x 844, shown at 2x) in a browser against the real backend with the Chandigarh demo
data. They are not photos of a handset: see "What has and has not been verified" in [`mobile/README.md`](../../mobile/README.md).
Differences from a phone: the map is OpenStreetMap tiles instead of the native map, and the glass blur is drawn by the browser rather than the system.

## Residents: CivicLoop

![Resident screens](resident-overview.png)

| Screen | File |
| --- | --- |
| Welcome slides (first launch) | [1](resident/00-welcome-1.png), [2](resident/00-welcome-2.png), [3](resident/00-welcome-3.png) |
| Sign in | [resident/01-sign-in.png](resident/01-sign-in.png) |
| Create an account (city and pincode) | [resident/02-create-account.png](resident/02-create-account.png) |
| Server address, with a connection test | [resident/03-server-address.png](resident/03-server-address.png) |
| My reports | [resident/04-my-reports.png](resident/04-my-reports.png) |
| Report waste, empty | [resident/05-report-empty.png](resident/05-report-empty.png) |
| Report waste, filled in with a photo | [resident/06-report-filled.png](resident/06-report-filled.png) |
| Report detail with map | [resident/07-report-detail.png](resident/07-report-detail.png) |
| Account | [resident/08-account.png](resident/08-account.png) |

## Crews: CivicLoop Crew

![Crew screens](crew-overview.png)

| Screen | File |
| --- | --- |
| Welcome slides (first launch) | [1](crew/00-welcome-1.png), [2](crew/00-welcome-2.png), [3](crew/00-welcome-3.png) |
| Sign in (no sign-up: a city admin makes crew accounts) | [crew/01-sign-in.png](crew/01-sign-in.png) |
| My jobs, most urgent first | [crew/02-jobs-todo.png](crew/02-jobs-todo.png) |
| Done jobs | [crew/03-jobs-done.png](crew/03-jobs-done.png) |
| Job detail: steps, map, start work | [crew/04-job-detail.png](crew/04-job-detail.png) |
| Vehicle location, before sharing | [crew/05-location.png](crew/05-location.png) |
| Vehicle location, sharing | [crew/06-location-sharing.png](crew/06-location-sharing.png) |
| Report a site | [crew/07-report.png](crew/07-report.png) |
| Account | [crew/08-account.png](crew/08-account.png) |
| Your route: stops in the planned order, progress, Navigate, open the whole route in Google Maps | [crew/11-route.png](crew/11-route.png) |

Regenerate: see `mobile/scripts/screenshots.mjs` and `mobile/scripts/contact_sheet.py`.

## The app's own dialogs and messages

No system alert is used anywhere. These are drawn by the app (see "No system popups" in [`mobile/README.md`](../../mobile/README.md)).

| Surface | File |
| --- | --- |
| Sign-out confirmation | [resident/09-sign-out-dialog.png](resident/09-sign-out-dialog.png) |
| Location explainer (shown before the phone's own prompt) | [resident/10-location-explainer.png](resident/10-location-explainer.png) |
| Pull to refresh | [resident/12-pull-to-refresh.png](resident/12-pull-to-refresh.png) |
| Page not found | [resident/13-not-found.png](resident/13-not-found.png) |
| Confirm "mark this cleanup as done" | [crew/09-confirm-done-dialog.png](crew/09-confirm-done-dialog.png) |
| Explainer before sharing the vehicle location | [crew/10-share-explainer.png](crew/10-share-explainer.png) |

Regenerate: `mobile/scripts/screenshots_dialogs.mjs`.
