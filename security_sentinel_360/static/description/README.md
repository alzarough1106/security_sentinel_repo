🛡️ Odoo Sentinel 360: Access Matrix, Session Security & Audit Trail — Odoo 16
Track every login session, audit every record change, and map every user permission across your entire Odoo database — with an interactive Access Right Matrix and real-time security dashboard.

Features
🗺️ Access Rights & Governance
Visual Access Right Matrix: Interactive User vs. Model grid displaying color-coded CRUD badges (Admin, RWCD, RW, Read). Filter by user groups, multi-company setups, or sensitive models, and export results directly to CSV.

User Permission Comparison: Select any two users to compare their effective permissions side-by-side. Instantly highlight matching vs. conflicting access rights across all models.

Reverse Permission Search: Query questions like "Who can delete account.move?" or "Who can modify HR records?" to instantly reveal all authorized users and their assigned security groups.

🌐 Live Session Security
Session Tracking: IP address, browser, browser version, OS, and device type captured automatically on every user login.

One-Click Kill Switch: Instantly terminate any suspicious or active session — forcing an immediate logout on the user's next request.

New Device Alerts: Automatic email notifications when a user logs in from an unrecognized device, browser, or IP address combination.

Idle Session Auto-Kill: Configurable scheduled action to automatically terminate sessions inactive beyond a set threshold.

📝 Comprehensive Audit Trail
Full CRUD Audit Log: Create, Read, Write, and Delete operations are logged automatically across business models and linked to the exact user session.

Module Install/Uninstall Tracking: Know who installed or removed any app, along with precise timestamps.

Granular Audit Rules: Fine-tune which models are tracked (enabled by default for business models; technical ir.* models are opt-in) to optimize performance.

📊 Analytics & Usability
Interactive Security Dashboard: KPI cards, trend lines, doughnut, and bar charts — every metric is clickable and drills straight into filtered record views.

Advanced Search & Grouping: Pre-built filters and group-by options for Sessions, Audit Logs, and Matrix views (by user, state, model, action, date granularity, and company).

Storage & Performance Notes
This module tracks Create/Update/Delete operations across business models by default. Actual database growth depends heavily on usage volume and which models are tracked — typical ranges are 100MB-1.5GB/year for small-to-medium teams (10-50 users), up to 10-15GB/year for larger deployments with heavy inventory/manufacturing activity. A configurable retention policy (default 365 days) keeps growth bounded.

For high-volume deployments, we recommend disabling audit tracking on line-item models (stock moves, order lines, journal items) via Audit Rules, which typically reduces log volume by 60-80% with minimal loss of audit value, since parent document state changes remain fully tracked.