"""
URL patterns for accounts app - Enhanced for GAM Platform
"""
from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from . import views

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

    path('partners/<int:user_id>/permissions/', views.get_partner_permissions, name='get-partner-permissions'),
    path('partners/<int:user_id>/permissions/update/', views.update_partner_permissions, name='update_partner_permissions'),

    path('partners/', views.list_partners, name='list_partners'),

    path('partners/<int:partner_id>/delete/', views.delete_partner_user, name='delete-partner-user'),

    # Partner admin management endpoints (admin manages partner admins)
    path('publishers/', views.list_partners_full, name='list_partners_full'),
    path('publishers/<int:user_id>/', views.update_partner, name='update_partner'),
    path('publishers/<int:user_id>/delete/', views.delete_partner_admin_user, name='delete_partner_admin_user'),

    # Payment details endpoints
    path('payment-details/', views.PaymentDetailView.as_view(), name='payment_details'),  # GET/POST/PUT for current user
    path('payment-details/all/', views.PaymentDetailListView.as_view(), name='payment_details_list'),  # GET all (admin)
    path('payment-details/<int:pk>/', views.PaymentDetailDetailView.as_view(), name='payment_detail_detail'),  # GET specific (admin)

    # Sites management endpoints
    path('sites/', views.SiteListView.as_view(), name='site_list'),  # GET all sites (admin sees all, publisher sees own)
    path('sites/sync-status/', views.sync_sites_status_view, name='sync_sites_status'),  # POST to sync site statuses from GAM

    # Sub-publisher management
    path('sub-publishers/', views.sub_publisher_list_create, name='sub_publisher_list_create'),
    path('sub-publishers/<int:sub_id>/', views.sub_publisher_detail, name='sub_publisher_detail'),
    path('sub-publishers/<int:sub_id>/tracking/', views.sub_publisher_tracking, name='sub_publisher_tracking'),

    # Subdomain management
    path('subdomains/', views.subdomain_list_create_delete, name='subdomain_list'),
    path('subdomains/<int:subdomain_id>/', views.subdomain_list_create_delete, name='subdomain_detail'),

    # Tutorials
    path('tutorials/', views.tutorial_list, name='tutorial_list'),
    path('tutorials/create/', views.tutorial_create, name='tutorial_create'),
    path('tutorials/<slug:slug>/', views.tutorial_detail, name='tutorial_detail'),

    # GAM credential management
    path('gam/status/', views.gam_status, name='gam_status'),
    path('gam/connect/', views.gam_connect, name='gam_connect'),
    path('gam/test/', views.gam_test, name='gam_test'),
    path('gam/disconnect/', views.gam_disconnect, name='gam_disconnect'),
    path('gam/oauth/init/', views.gam_oauth_init, name='gam_oauth_init'),
    path('gam/oauth/callback/', views.gam_oauth_callback, name='gam_oauth_callback'),
]