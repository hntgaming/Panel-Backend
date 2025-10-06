"""
URL patterns for accounts app - Enhanced for GAM Platform
"""
from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from . import views, rbac_views

app_name = 'accounts'

urlpatterns = [
    # Authentication endpoints
    path('register/', views.UserRegistrationView.as_view(), name='register'),
    path('login/', views.user_login_view, name='login'),
    path('logout/', views.user_logout_view, name='logout'),
    
    # JWT token refresh
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    
    # User profile management
    path('profile/', views.update_profile_view, name='profile'),
    path('change-password/', views.change_password_view, name='change_password'),
    path('me/permissions/', views.user_permissions_view, name='user_permissions'),
    
    # Dashboard
    path('dashboard/', views.user_dashboard_view, name='dashboard'),
    
    # Admin-only endpoints
    path('users/', views.UserListView.as_view(), name='user_list'),
    path('users/<int:pk>/role/', views.UserRoleUpdateView.as_view(), name='user_role_update'),

    path('reset/<uidb64>/<token>/',views.CustomPasswordResetConfirmView.as_view(),name='password_reset_confirm'),
    path("reset_password/", views.PasswordResetConfirmAPIView.as_view(), name="reset-password-api"),
    
    path('users/<int:user_id>/status/', views.update_user_status_view, name='update_user_status'),

    path('users/<int:user_id>/permissions/', views.update_partner_permissions, name='update_partner_permissions'),
    path('partners/<int:user_id>/permissions/', views.get_partner_permissions, name='get-partner-permissions'),

    path('partners/', views.list_partners, name='list_partners'),

    path('partners/<int:partner_id>/delete/', views.delete_partner_user, name='delete-partner-user'),

    # RBAC endpoints (Admin only)
    path('rbac/permissions/', rbac_views.PermissionListView.as_view(), name='rbac-permissions'),
    path('rbac/role-permissions/', rbac_views.RolePermissionListView.as_view(), name='rbac-role-permissions'),
    path('rbac/users/<int:user_id>/permissions/', rbac_views.UserPermissionOverridesView.as_view(), name='rbac-user-permissions'),
    path('rbac/partners/<int:partner_id>/publishers/', rbac_views.PartnerPublisherAccessView.as_view(), name='rbac-partner-publishers'),
    path('rbac/parents/<int:parent_id>/network/', rbac_views.ParentNetworkAssignmentView.as_view(), name='rbac-parent-network'),
    path('rbac/audit-logs/', rbac_views.PermissionAuditLogView.as_view(), name='rbac-audit-logs'),
    path('rbac/me/claims/', rbac_views.user_claims_view, name='rbac-user-claims'),

]