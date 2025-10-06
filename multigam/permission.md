# Partner Permission System Blueprint

## Goals
- Equip referral partners with role-aware access that can be toggled without code changes.
- Ensure partners only see assigned GAM entities and their associated reports, alerts, and tickets.
- Provide admins with a clear workflow to provision partners, assign child accounts, and manage trust/settings.

## Existing Foundation
- `accounts.User` already distinguishes `admin` vs `partner` roles and includes an `status` flag for activation (`backend/accounts/models.py:9`).
- Feature toggles live in `PartnerPermission` (`backend/accounts/models.py:94`) with enums for:
  - `manage_mcm_invites`
  - `verify_accounts`
  - `access_reports`
  - `manage_alerts`
  - `access_tickets`
- Child accounts are assigned through `AssignedPartnerChildAccount`; signals propagate partner IDs to report rows (`backend/gam_accounts/models.py:225`, `backend/reports/signals.py:7`).
- Reporting endpoints already scope data to assigned invitations (`backend/reports/views.py:41`).

## High-Level Architecture
1. **Permission Records in DB**  
   - Maintain one row per permission toggle per partner.  
   - Keep enum values in a shared constant file for backend/frontend synchronization.

2. **Permission Service Layer**  
   - A helper (e.g., `accounts/permissions.py`) to load, cache, and evaluate permissions:  
     `has_partner_permission(user, Perm.ACCESS_REPORTS)`  
   - Cache by `user_id`; invalidate via signals on `PartnerPermission` create/update/delete.

3. **Admin Management APIs**
   - Continue using `UserRegistrationView` to create partners; supply permission list in payload and write all toggles through `PartnerPermission`.  
   - `update_partner_permissions` (PATCH) already accepts toggle sets; extend response to include normalized permission summary for UI.
   - Add `GET /api/auth/partners/<id>/permissions/summary` returning boolean matrix plus metadata (last updated, updated by, notes).

4. **Partner Self-Discovery Endpoint**
   - `GET /api/auth/me/permissions` so frontend can hide/disallow sections immediately after login.  
   - Response contains:
     ```json
     {
       "status": "active",
       "permissions": {
         "manage_mcm_invites": false,
         "verify_accounts": true,
         ...
       }
     }
     ```

5. **Runtime Enforcement**
   - Wrap partner-facing views with:
     - A mixin that filters querysets by `AssignedPartnerChildAccount`.
     - Permission checks mapping actions → required toggle:
       | Feature | Required Permission | Example Endpoints |
       |---------|---------------------|-------------------|
       | Manage MCM Invites | `manage_mcm_invites` | `AssignPartnerToChildAccountView`, `SendMCMInvitationView`, manual entry |
       | Verify Accounts | `verify_accounts` | account verification flows |
       | Access Reports | `access_reports` | `ReportDataListView`, analytics, exports |
       | Manage Alerts | `manage_alerts` | smart alerts CRUD |
       | Access Tickets | `access_tickets` | ticket board endpoints |
   - Return `403` with a clear message when permission is missing.

6. **Admin Visibility**
   - Register `PartnerPermission` and `AssignedPartnerChildAccount` in Django admin, list toggles inline, show last login/status.
   - Provide dashboard endpoint summarizing partner trust state (active/inactive, invited date, assigned networks count, permission set).

7. **Frontend Expectations**
   - Management modal consumes permission list from `/partners/<id>/permissions/summary`.
   - Dashboard navigation uses `/auth/me/permissions` to hide blocked sections.
   - Toggle changes call `PATCH /api/auth/users/<id>/permissions/`.

8. **Auditing & Trust Signals**
   - Optional `PartnerProfile` model for trust level, notes, referral metadata.
   - Log every permission change with admin user + timestamp (model or structured logging).

9. **Testing Strategy**
   - Unit tests for helper service verifying caching and fallbacks.
   - API tests ensuring 403 for partners lacking specific toggles.
   - Regression tests for assignment scoping (partner cannot access unassigned invitations even with permission).
   - Smoke tests for admin workflows (create partner with toggles, update toggles, ensure frontend endpoints reflect changes).

## Implementation Checklist
1. **Constants & Helper**
   - Create `accounts/permissions.py` enumerating permission IDs and providing `load_permissions(user_id)` with caching.
   - Place shared permission constants in `backend/reports/constants.py` (or a dedicated permissions module) for reuse.

2. **Signals**
   - Add post-save/delete receivers on `PartnerPermission` to clear cached permissions.

3. **API Enhancements**
   - Extend existing serializers to emit standardized permission payloads.
   - Add `GET /api/auth/me/permissions` view.
   - Harden `get_partner_permissions` with `IsSelfOrAdmin` guard.

4. **Enforcement**
   - Update GAM invitations, verification, alerts, tickets, and reporting views to check `has_partner_permission` before processing.
   - Add mixin for queryset scoping to reduce duplication.

5. **Admin & UI**
   - Register partner-related models in Django admin.
   - Update admin dashboard endpoints to surface permission summary and trust notes.

6. **Documentation**
   - Maintain this `partner.md` blueprint.
   - Document sample payloads for creation and updates:
     ```json
     {
       "email": "contact@partner.com",
       "permissions": [
         {"permission": "access_reports"},
         {"permission": "manage_alerts"}
       ]
     }
     ```

7. **Verification**
   - Add integration tests ensuring each toggle blocks/unblocks the corresponding UI feature.
   - Ensure cached permissions bust after updates.

## Future Enhancements
- Group permissions into presets (e.g., “Viewer”, “Operator”) to simplify admin workflows.
- Introduce expiration or review dates for partner access.
- Add webhooks/notifications when a partner loses access due to manual toggles or trust score changes.

---

This document captures the full plan from our discussions; drop it into `partner.md` and iterate from here.
