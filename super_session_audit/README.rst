# 🛡️ Super Session Management & Audit Trail — Odoo 18 CE!

Track every login session and audit every record change across your entire
Odoo database — with a live, color-coded dashboard.

## Features

- **Session Tracking**: IP address, browser, browser version, OS, and device
  type captured automatically on every login.
- **Kill Switch**: Instantly terminate any active session — the affected
  user is force-logged-out on their next request (or immediately, if it's
  their own current session).
- **New Device Alerts**: Automatic email notification when a user logs in
  from an unrecognized device/browser/IP combination.
- **Idle Session Auto-Kill**: Configurable scheduled action to automatically
  terminate sessions inactive beyond a threshold.
- **Full Audit Trail**: Create / Update / Delete operations are logged
  automatically across business models, linked to the exact session they
  occurred in.
- **Module Install/Uninstall Tracking**: Know who installed or removed any
  app, and when.
- **Audit Rules**: Fine-tune which models are tracked (enabled by default
  for business models; technical `ir.*` models are opt-in).
- **Interactive Dashboard**: KPI cards, trend lines, doughnut/bar charts —
  every element is clickable and drills straight into the filtered list.
- **Advanced Search**: Pre-built filters and group-by options for both
  Sessions and Audit Logs (by user, state, model, action, date granularity).

## Storage & Performance Notes

This module tracks Create/Update/Delete operations across business models by default. Actual database growth depends heavily on usage volume and which models are tracked — typical ranges are 100MB-1.5GB/year for small-to-medium teams (10-50 users), up to 10-15GB/year for larger deployments with heavy inventory/manufacturing activity. A configurable retention policy (default 365 days) keeps growth bounded. 

For high-volume deployments, we recommend disabling audit tracking on line-item models (stock moves, order lines, journal items) via Audit Rules, which typically reduces log volume by 60-80% with minimal loss of audit value, since parent document state changes remain fully tracked.