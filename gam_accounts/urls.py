# gam_accounts/urls.py - CLEANED VERSION

from django.urls import path
from . import views

app_name = 'gam_accounts'

urlpatterns = [
    # ========================================================================
    # GAM NETWORK ENDPOINTS
    # ========================================================================
    
    # Network CRUD operations
    path(
        'networks/', 
        views.GAMNetworkListCreateView.as_view(), 
        name='gam-networks-list'
    ),
    path(
        'networks/<int:pk>/', 
        views.GAMNetworkDetailView.as_view(), 
        name='gam-networks-detail'
    ),
    
    # ========================================================================
    # MCM INVITATION ENDPOINTS
    # ========================================================================
    
    # Invitation CRUD operations
    path(
        'mcm-invitations/', 
        views.MCMInvitationListCreateView.as_view(), 
        name='mcm-invitations-list'
    ),
    path(
        'mcm-invitations/<int:pk>/', 
        views.MCMInvitationDetailView.as_view(), 
        name='mcm-invitations-detail'
    ),
    
    # MCM invitation creation and sending removed - no longer needed for managed inventory publisher dashboard
    

    # ========================================================================
    # PUBLISHER ASSIGNMENT ENDPOINTS
    # ========================================================================
    
    path(
        'assign-publisher/', 
        views.AssignPublisherToChildAccountView.as_view(), 
        name='assign-publisher-to-child'
    ),
    path(
        'publishers/<int:publisher_id>/assigned-accounts/', 
        views.GetAssignedAccountsForPublisherView.as_view(), 
        name='assigned-accounts-for-publisher'
    ),
    
    # ========================================================================
    # ADMIN ENDPOINTS
    # ========================================================================
    
    # Admin MCM management endpoints removed - no longer needed for managed inventory publisher dashboard
    path(
        'dashboard-stats/',
        views.DashboardStatsView.as_view(),
        name='dashboard-stats'
    ),
]

# ============================================================================
# API ENDPOINT REFERENCE - CLEANED VERSION
# ============================================================================
"""
🎯 GAM ACCOUNTS API ENDPOINTS - CLEANED & SIMPLIFIED

All endpoints are directly defined and clickable in your IDE!

=== GAM NETWORK ENDPOINTS ===

📋 Networks:
├── GET    /api/gam/networks/                     → GAMNetworkListCreateView
├── POST   /api/gam/networks/                     → GAMNetworkListCreateView
├── GET    /api/gam/networks/{id}/                → GAMNetworkDetailView
├── PUT    /api/gam/networks/{id}/                → GAMNetworkDetailView
├── PATCH  /api/gam/networks/{id}/                → GAMNetworkDetailView
└── DELETE /api/gam/networks/{id}/                → GAMNetworkDetailView

=== MCM INVITATION ENDPOINTS ===

📧 Invitations (Read-only for managed inventory):
├── GET    /api/gam/mcm-invitations/              → MCMInvitationListCreateView
├── GET    /api/gam/mcm-invitations/{id}/         → MCMInvitationDetailView
├── PUT    /api/gam/mcm-invitations/{id}/         → MCMInvitationDetailView
├── PATCH  /api/gam/mcm-invitations/{id}/         → MCMInvitationDetailView
└── DELETE /api/gam/mcm-invitations/{id}/         → MCMInvitationDetailView

=== PUBLISHER ASSIGNMENT ENDPOINTS ===

🔧 Assignments:
├── POST   /api/gam/assign-publisher/              → AssignPublisherToChildAccountView
└── GET    /api/gam/publishers/{id}/assigned-accounts/ → GetAssignedAccountsForPublisherView

=== ADMIN ENDPOINTS ===

👨‍💼 Admin:
└── GET    /api/gam/dashboard-stats/             → DashboardStatsView

=== QUERY PARAMETERS ===

🔍 Networks (?):
- type: parent|child
- status: active|inactive|pending
- search: Search in name/code/description

🔍 MCM Invitations (?):
- status: pending|accepted|declined|expired|awaiting_manual_send|api_error
- parent_network: NETWORK_CODE
- delegation_type: MANAGED_INVENTORY|MANAGE_ACCOUNT
- created_after: YYYY-MM-DD
- created_before: YYYY-MM-DD

🔍 Permissions (?):
- user: {user_id}
- network: {network_id}
- permission_type: access_reports
"""