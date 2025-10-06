RBAC (Role-Based Access Control) for GAM Sentinel

Version: 2.0 • Status: Production Ready ✅ IMPLEMENTED

## 0) Executive Summary

This README documents the implemented RBAC system for the GAM Sentinel platform. The system defines three roles—ADMIN, PARENT, PARTNER—with a permission system that matches the actual frontend navigation structure. Authorization is enforced on the backend using permission checks and object-scope filters. The system uses JWT tokens stored in HttpOnly cookies for secure authentication.

## 1) Roles & Access Model

### Roles

**ADMIN (superuser)**
- Global access to all data and actions
- Only role allowed to Settings and Manage Partners pages
- Gets all 8 permissions by default

**PARENT**
- Full access within their assigned network (restricted to their parent_network_id)
- Gets 6 configurable permissions (excludes admin-only permissions)
- Cannot access Settings or Manage Partners

**PARTNER**
- Access only to publishers explicitly assigned to that partner
- All permissions are configurable from the frontend (no default permissions)
- Cannot access Settings or Manage Partners

### Golden Rules
- Every request must pass (A) permission check and (B) object-scope filter
- Do not trust the UI for authorization; backend enforces all checks
- Use HttpOnly cookies for JWT tokens; no readable roles/permissions in cookies

## 2) Permission Catalog (IMPLEMENTED)

### Current Permission Structure (Matches Frontend Navigation)

**Admin-only permissions:**
- `manage_partners` - Manage Partners page
- `settings` - Settings page

**Parent/Partner configurable permissions:**
- `managed_sites` - Managed Sites
- `mcm_invites` - MCM Invites (requires parent_gam_network)
- `verification` - Verification
- `reports` - Reports
- `smart_alerts` - Smart Alerts
- `ticket_board` - Ticket Board

### Permission Defaults (IMPLEMENTED)
- **ADMIN** → all 8 permissions
- **PARENT** → 6 permissions (excludes `manage_partners`, `settings`)
- **PARTNER** → 0 default permissions (all configurable via frontend)

## 3) Data Model (IMPLEMENTED)

### Django Models

```python
# User model with RBAC fields
class User(AbstractUser):
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='PARTNER')
    permissions_version = models.IntegerField(default=1)
    # ... other fields

# RBAC Permission system
class Permission(TimeStampedModel):
    key = models.CharField(max_length=100, unique=True)
    description = models.TextField()
    category = models.CharField(max_length=50, blank=True)

class RolePermission(TimeStampedModel):
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    permission = models.ForeignKey(Permission, on_delete=models.CASCADE)

class UserPermissionOverride(TimeStampedModel):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    permission = models.ForeignKey(Permission, on_delete=models.CASCADE)
    allowed = models.BooleanField()

# Partner-specific permissions (legacy compatibility)
class PartnerPermission(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    permission = models.CharField(max_length=50, choices=PermissionChoices.choices)
    parent_gam_network = models.ForeignKey('gam_accounts.GAMNetwork', null=True, blank=True)

# Publisher access control
class PartnerPublisherAccess(TimeStampedModel):
    partner = models.ForeignKey(User, on_delete=models.CASCADE)
    publisher = models.ForeignKey('gam_accounts.MCMInvitation', on_delete=models.CASCADE)

# Parent network assignments
class ParentNetwork(TimeStampedModel):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    parent_network = models.ForeignKey('gam_accounts.GAMNetwork', on_delete=models.CASCADE)
```

## 4) Effective Permissions (IMPLEMENTED)

### RBACService Implementation

```python
@classmethod
def get_effective_permissions(cls, user: User) -> set:
    # 1. Get role-based permissions
    role_permissions = RolePermission.objects.filter(
        role=user.role.upper()
    ).select_related('permission')
    
    permissions = {role_perm.permission.key for role_perm in role_permissions}
    
    # 2. Apply user-specific overrides
    overrides = UserPermissionOverride.objects.filter(
        user=user
    ).select_related('permission')
    
    for override in overrides:
        if override.allowed:
            permissions.add(override.permission.key)
        else:
            permissions.discard(override.permission.key)
    
    # 3. Apply partner permissions (for partner users)
    if user.role.upper() == 'PARTNER':
        partner_permissions = PartnerPermission.objects.filter(user=user)
        for partner_perm in partner_permissions:
            permissions.add(partner_perm.permission)
    
    return permissions
```

## 5) Object Scope Filters (IMPLEMENTED)

### User Scope Service

```python
@classmethod
def get_user_scope(cls, user: User) -> dict:
    scope = {
        'publisher_ids': None,
        'parent_network_id': None,
        'is_admin': user.role.upper() == 'ADMIN'
    }
    
    if user.role.upper() == 'ADMIN':
        # Admin sees all
        scope['publisher_ids'] = None
    elif user.role.upper() == 'PARENT':
        # Parent sees their network
        try:
            parent_network = ParentNetwork.objects.get(user=user)
            scope['parent_network_id'] = parent_network.parent_network.id
        except ParentNetwork.DoesNotExist:
            pass
    elif user.role.upper() == 'PARTNER':
        # Partner sees assigned publishers
        assigned_publishers = PartnerPublisherAccess.objects.filter(
            partner=user
        ).values_list('publisher_id', flat=True)
        scope['publisher_ids'] = list(assigned_publishers)
    
    return scope
```

## 6) Authentication & Cookies (IMPLEMENTED)

### JWT Implementation
- Short-lived Access JWT (15 minutes) with user claims
- Refresh token in HttpOnly cookie
- Secure cookie settings: HttpOnly, Secure, SameSite=Lax

### Django Settings
```python
SESSION_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SECURE = True
```

## 7) Login Flow (IMPLEMENTED)

### API Endpoints
- `POST /api/auth/login/` → authenticate and return JWT tokens
- `POST /api/auth/logout/` → clear tokens
- `GET /api/auth/me/permissions/` → return user permissions and claims

### Response Format
```json
{
  "user_id": 1,
  "email": "admin@gamplatform.com",
  "role": "ADMIN",
  "is_admin": true,
  "permissions": {
    "manage_partners": true,
    "settings": true,
    "managed_sites": true,
    "mcm_invites": true,
    "verification": true,
    "reports": true,
    "smart_alerts": true,
    "ticket_board": true
  },
  "effective_permissions": [
    "manage_partners", "settings", "managed_sites", 
    "mcm_invites", "verification", "reports", 
    "smart_alerts", "ticket_board"
  ],
  "assigned_accounts_count": 0,
  "parent_network": null,
  "permissions_version": 1
}
```

## 8) Route Guards (IMPLEMENTED)

### Permission Decorators
```python
@require_permission('reports')
def list_reports(request):
    # View implementation
    pass

@require_permission('manage_partners')
def manage_partners(request):
    # Admin-only view
    pass
```

### Permission Classes
```python
class AdminOnlyPermission(permissions.BasePermission):
    def has_permission(self, request, view):
        return (
            request.user and 
            request.user.is_authenticated and 
            request.user.role == 'ADMIN'
        )

class HasPermission(permissions.BasePermission):
    def has_permission(self, request, view):
        permission_key = view.get_permission_key()
        return RBACService.has_permission(request.user, permission_key)
```

## 9) Frontend Behavior (IMPLEMENTED)

### Permission Context
```javascript
const { isAdmin, hasPermission, loading } = usePermissions();

// Navigation based on permissions
if (isAdmin || hasPermission("reports")) {
    // Show Reports menu item
}

if (isAdmin || hasPermission("manage_partners")) {
    // Show Manage Partners menu item (admin only)
}
```

### Managed Partners Page
- Admin can create partners with configurable permissions
- Admin can edit partner permissions via frontend
- All permissions are togglable except admin-only permissions

## 10) API Surface (IMPLEMENTED)

### Authentication Endpoints
- `POST /api/auth/login/` → authenticate user
- `POST /api/auth/logout/` → logout user
- `GET /api/auth/me/permissions/` → get user permissions

### Partner Management (Admin Only)
- `GET /api/auth/partners/` → list all partners
- `GET /api/auth/partners/{id}/permissions/` → get partner permissions
- `PATCH /api/auth/users/{id}/permissions/` → update partner permissions

### RBAC Management (Admin Only)
- `GET /api/auth/rbac/permissions/` → list all permissions
- `GET /api/auth/rbac/role-permissions/` → list role permissions
- `GET /api/auth/rbac/users/{id}/permissions/` → get user permission overrides
- `PATCH /api/auth/rbac/users/{id}/permissions/` → update user permission overrides

### Permission Update Format
```json
{
  "permissions": [
    {"permission": "reports"},
    {"permission": "smart_alerts"},
    {"permission": "ticket_board"},
    {
      "permission": "mcm_invites",
      "parent_gam_network": 123
    }
  ]
}
```

## 11) Operational Rules (IMPLEMENTED)

- **Admin** → everything, including Settings and Manage Partners
- **Parent** → everything in their assigned network; no Settings/Manage Partners
- **Partner** → only assigned publishers; permissions configurable via frontend
- Every endpoint checks permission + scope
- JWT tokens stored in HttpOnly cookies
- Permission versioning for cache invalidation
- Audit logging for permission changes

## 12) Testing Results ✅

### Verified Functionality
- ✅ Admin can access Settings and Manage Partners; others cannot
- ✅ Parent users get network-restricted permissions
- ✅ Partner users get configurable permissions from frontend
- ✅ Partner permissions are applied correctly after login
- ✅ All restricted routes return 403 without proper permissions
- ✅ Cookies are HttpOnly, Secure, SameSite=Lax
- ✅ Frontend navigation respects permission checks
- ✅ Partner creation and permission editing works end-to-end

### Test Data
```json
// Admin User Permissions
{
  "permissions": {
    "manage_partners": true,
    "settings": true,
    "managed_sites": true,
    "mcm_invites": true,
    "verification": true,
    "reports": true,
    "smart_alerts": true,
    "ticket_board": true
  }
}

// Partner User Permissions (Configurable)
{
  "permissions": {
    "reports": true,
    "smart_alerts": true,
    "ticket_board": true
  }
}
```

## 13) Management Commands (IMPLEMENTED)

### Setup RBAC System
```bash
python manage.py setup_rbac --reset
```

This command:
- Creates all permission records
- Sets up role permission defaults
- Handles both new installations and resets

## 14) Security Implementation ✅

- ✅ HttpOnly, Secure, SameSite=Lax cookies
- ✅ Short-lived JWT tokens (15 minutes)
- ✅ No readable roles/permissions in cookies
- ✅ Backend enforcement of all permissions
- ✅ Permission versioning for cache invalidation
- ✅ Audit logging for permission changes

## 15) Deployment Status ✅

- ✅ Frontend: Updated with correct permission keys
- ✅ Backend: All RBAC components implemented
- ✅ Database: All tables created and populated
- ✅ Server: Deployed and running in production
- ✅ Testing: End-to-end functionality verified

## 16) Current Implementation Status

### ✅ Completed Components
1. **RBAC Models**: Permission, RolePermission, UserPermissionOverride, PartnerPermission
2. **RBAC Service**: Effective permissions calculation and user scope
3. **Permission Decorators**: @require_permission and permission classes
4. **API Views**: All RBAC management endpoints
5. **Frontend Integration**: Permission context and navigation guards
6. **Partner Management**: Create/edit partners with configurable permissions
7. **Database Setup**: Management command for RBAC initialization
8. **Authentication**: JWT-based auth with secure cookies

### 🎯 Key Features Working
- **Admin Access**: Full access to all features including Settings and Manage Partners
- **Parent Users**: Network-restricted access to all features except admin-only
- **Partner Users**: Configurable permissions via frontend interface
- **Permission Enforcement**: Backend validates all permissions on every request
- **Frontend Sync**: Navigation and UI elements respect permission checks
- **Real-time Updates**: Permission changes take effect immediately

## 17) FAQ

**Q: How do we grant a Partner access to specific publishers?**
A: Use the `PartnerPublisherAccess` model to assign publishers to partners. This is separate from permission management.

**Q: Can a Parent user access Settings?**
A: No. Only ADMIN users can access Settings and Manage Partners pages.

**Q: How do we add new permissions?**
A: Add the permission to the `setup_rbac` command, run the command, and update frontend permission checks.

**Q: Are partner permissions cached?**
A: Yes, permissions are cached with versioning. Changes automatically invalidate the cache.

**Q: How do we test the RBAC system?**
A: Use the test endpoints and verify that users get correct permissions based on their role and assignments.

---

**Last Updated**: January 2025  
**Status**: ✅ Production Ready - Fully Implemented and Tested