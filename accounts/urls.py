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
    path('public-signup/', views.public_signup_view, name='public_signup'),
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

    # Publisher management endpoints
    path('publishers/', views.list_publishers, name='list_publishers'),
    path('publishers/<int:user_id>/', views.update_publisher, name='update_publisher'),  # PUT to update
    path('publishers/<int:user_id>/permissions/', views.get_publisher_permissions, name='get_publisher_permissions'),
    path('users/<int:user_id>/permissions/', views.update_publisher_permissions, name='update_publisher_permissions'),
    path('publishers/<int:user_id>/delete/', views.delete_publisher_user, name='delete_publisher_user'),

    # Payment details endpoints
    path('payment-details/', views.PaymentDetailView.as_view(), name='payment_details'),  # GET/POST/PUT for current user
    path('payment-details/all/', views.PaymentDetailListView.as_view(), name='payment_details_list'),  # GET all (admin)
    path('payment-details/<int:pk>/', views.PaymentDetailDetailView.as_view(), name='payment_detail_detail'),  # GET specific (admin)

    # Sites management endpoints
    path('sites/', views.SiteListView.as_view(), name='site_list'),  # GET all sites (admin sees all, publisher sees own)

    # Network ID management endpoints
    path('publishers/fetch-network-ids/', views.fetch_missing_network_ids_view, name='fetch_network_ids'),  # POST to fetch missing network IDs from GAM

]