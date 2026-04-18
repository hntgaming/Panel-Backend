"""
Clean authentication views for API-only endpoints
No CSRF decorators needed - using JWT authentication only
"""
import logging
from rest_framework import status, generics, permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import login
from django.utils import timezone
from django.contrib.auth.views import PasswordResetConfirmView
from django.http import JsonResponse
from rest_framework.views import APIView
from django.contrib.auth.tokens import default_token_generator
from django.utils.http import urlsafe_base64_decode
from django.contrib.auth.password_validation import validate_password
from django.conf import settings
from core.models import StatusChoices
# Removed gam_accounts dependencies

from .models import PublisherPermission, User, Site, GAMCredential
from reports.gam_client import GAMClientService

logger = logging.getLogger(__name__)
DEBUG = settings.DEBUG
from .permissions import load_publisher_permissions
from .serializers import (
    PublisherListSerializer,
    UserRegistrationSerializer,
    UserLoginSerializer,
    UserProfileSerializer,
    UserRoleUpdateSerializer,
    ChangePasswordSerializer,
    SiteSerializer
)


class IsAdminUser(permissions.BasePermission):
    """
    Custom permission to only allow admin users
    """
    def has_permission(self, request, view):
        return (
            request.user and 
            request.user.is_authenticated and 
            request.user.role.upper() == 'ADMIN'
        )


class UserRegistrationView(generics.CreateAPIView):
    """
    User registration endpoint with role-based creation
    POST /api/auth/register/
    """
    queryset = User.objects.all()
    serializer_class = UserRegistrationSerializer
    permission_classes = [AllowAny]
    
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        
        # Generate JWT tokens
        refresh = RefreshToken.for_user(user)
        
        return Response({
            'message': 'User registered successfully',
            'user': UserProfileSerializer(user).data,
            'tokens': {
                'refresh': str(refresh),
                'access': str(refresh.access_token),
            }
        }, status=status.HTTP_201_CREATED)


@api_view(['POST'])
@permission_classes([AllowAny])
def user_login_view(request):
    """
    Enhanced user login endpoint with IP tracking
    POST /api/auth/login/
    """
    try:
        serializer = UserLoginSerializer(
            data=request.data,
            context={'request': request}
        )
        
        if serializer.is_valid():
            user = serializer.validated_data['user']
            
            # Update last login IP
            try:
                x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
                if x_forwarded_for:
                    ip = x_forwarded_for.split(',')[0].strip()
                else:
                    ip = request.META.get('REMOTE_ADDR', '')
                
                if ip:
                    user.last_login_ip = ip
                    user.save(update_fields=['last_login_ip'])
            except Exception as ip_error:
                # Log IP update error but don't fail login
                logger.warning(f"Failed to update login IP: {str(ip_error)}")
            
            # Generate JWT tokens
            try:
                refresh = RefreshToken.for_user(user)
            except Exception as token_error:
                logger.error(f"Failed to generate JWT tokens: {str(token_error)}")
                return Response({
                    'error': 'Failed to generate authentication tokens. Please try again.'
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            
            # Serialize user data
            try:
                user_data = UserProfileSerializer(user).data
            except Exception as serialization_error:
                logger.error(f"Failed to serialize user data: {str(serialization_error)}")
                # Return minimal user data if serialization fails
                user_data = {
                    'id': user.id,
                    'email': user.email,
                    'first_name': user.first_name,
                    'last_name': user.last_name,
                    'role': user.role,
                }
            
            return Response({
                'message': 'Login successful',
                'user': user_data,
                'tokens': {
                    'refresh': str(refresh),
                    'access': str(refresh.access_token),
                }
            }, status=status.HTTP_200_OK)
        
        # Return validation errors
        return Response(
            serializer.errors,
            status=status.HTTP_400_BAD_REQUEST
        )
    
    except Exception as e:
        # Log the full error for debugging
        import traceback
        error_trace = traceback.format_exc()
        logger.error(f"Login view error: {str(e)}\n{error_trace}")
        return Response({
            'error': 'An error occurred during login. Please try again.'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def user_logout_view(request):
    """
    User logout endpoint - Fixed version
    POST /api/auth/logout/
    """
    try:
        refresh_token = request.data.get('refresh_token')
        
        if not refresh_token:
            return Response({
                'error': 'refresh_token is required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Try to blacklist the refresh token
        token = RefreshToken(refresh_token)
        token.blacklist()
        
        return Response({
            'message': 'Logout successful'
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        # More specific error handling
        error_msg = str(e)
        
        # Handle specific token errors
        if 'Token is blacklisted' in error_msg:
            return Response({
                'message': 'Already logged out'
            }, status=status.HTTP_200_OK)
        
        if 'Invalid token' in error_msg or 'token_type' in error_msg:
            return Response({
                'error': 'Invalid refresh token provided'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Log the actual error for debugging
        logger.error(f"Logout error: {error_msg}")
        
        return Response({
            'error': f'Logout failed: {error_msg}'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    
class UserProfileView(generics.RetrieveUpdateAPIView):
    """
    User profile endpoint - get and update user info
    GET/PUT /api/auth/profile/
    """
    serializer_class = UserProfileSerializer
    permission_classes = [IsAuthenticated]
    
    def get_object(self):
        return self.request.user


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def user_permissions_view(request):
    """
    Get current user's permissions
    GET /api/auth/me/permissions
    """
    user = request.user
    
    # Simplified permissions for managed inventory
    effective_permissions = load_publisher_permissions(user)
    
    # Convert permissions to frontend-compatible format
    permissions = {}
    for perm in effective_permissions:
        permissions[perm] = True
    
    return Response({
        'user_id': user.id,
        'email': user.email,
        'role': user.role,
        'status': user.status,
        'is_admin': user.role.upper() == 'ADMIN',
        'permissions': permissions,
        'can_modify_gam_status': user.role.upper() == 'ADMIN',
    })


class ChangePasswordView(generics.UpdateAPIView):
    """
    Change password endpoint
    PUT /api/auth/change-password/
    """
    serializer_class = ChangePasswordSerializer
    permission_classes = [IsAuthenticated]
    
    def get_object(self):
        return self.request.user
    
    def update(self, request, *args, **kwargs):
        serializer = self.get_serializer(
            data=request.data,
            context={'request': request}
        )
        
        if serializer.is_valid():
            serializer.save()
            return Response({
                'message': 'Password changed successfully'
            }, status=status.HTTP_200_OK)
        
        return Response(
            serializer.errors,
            status=status.HTTP_400_BAD_REQUEST
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def user_dashboard_view(request):
    """
    Enhanced dashboard endpoint with role-based data
    GET /api/auth/dashboard/
    """
    user = request.user
    
    dashboard_data = {
        'message': f'Welcome, {user.get_full_name()}!',
        'user': UserProfileSerializer(user).data,
        'user_role': user.role,
        'is_admin': user.role.upper() == 'ADMIN',
    }
    
    if user.role.upper() == 'ADMIN':
        dashboard_data['platform_stats'] = {
            'total_users': User.objects.count(),
            'active_users': User.objects.filter(status='active').count(),
            'admin_users': User.objects.filter(role='admin').count(),
            'partner_admin_users': User.objects.filter(role='partner_admin').count(),
        }
    elif user.role == 'partner_admin':
        publisher_permissions = list(
            PublisherPermission.objects.filter(user=user).values_list('permission', flat=True)
        )
        dashboard_data['partner_stats'] = {
            'assigned_accounts': 1,
            'accessible_reports': 1 if 'reports' in publisher_permissions else 0,
            'managed_websites': user.sites.count(),
        }
    
    return Response(dashboard_data, status=status.HTTP_200_OK)


# Admin-only views
class UserListView(generics.ListAPIView):
    """
    List all users (Admin only)
    GET /api/auth/users/
    """
    queryset = User.objects.all().order_by('-date_joined')
    serializer_class = UserProfileSerializer
    permission_classes = [IsAdminUser]


class UserRoleUpdateView(generics.UpdateAPIView):
    """
    Update user role and status (Admin only)
    PUT /api/auth/users/{id}/role/
    """
    queryset = User.objects.all()
    serializer_class = UserRoleUpdateSerializer
    permission_classes = [IsAdminUser]
    
    def update(self, request, *args, **kwargs):
        user = self.get_object()
        
        # Prevent self-demotion
        if user == request.user and request.data.get('role') != 'admin':
            return Response({
                'error': 'You cannot change your own admin role'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        serializer = self.get_serializer(
            user, 
            data=request.data, 
            context={'request': request}
        )
        
        if serializer.is_valid():
            serializer.save()
            return Response({
                'message': f'User role updated successfully',
                'user': UserProfileSerializer(user).data
            }, status=status.HTTP_200_OK)
        
        return Response(
            serializer.errors,
            status=status.HTTP_400_BAD_REQUEST
        )
    
class CustomPasswordResetConfirmView(PasswordResetConfirmView):
    def form_valid(self, form):
        response = super().form_valid(form)

        user = form.user
        # Partner admins are activated automatically after password reset
        if user.role == user.UserRole.PARTNER_ADMIN and user.status == StatusChoices.PENDING_APPROVAL:
            user.status = StatusChoices.ACTIVE
            user.save(update_fields=["status"])

        return response
    

@api_view(['PATCH'])
@permission_classes([IsAdminUser])
def update_user_status_view(request, user_id):
    """
    PATCH /api/auth/users/<user_id>/status/
    Body: { "status": "active" or "inactive" }
    """
    try:
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        return Response({"error": "User not found."}, status=status.HTTP_404_NOT_FOUND)
    
    new_status = request.data.get("status")
    if new_status not in [StatusChoices.ACTIVE, StatusChoices.INACTIVE]:
        return Response(
            {"error": "Invalid status. Allowed values: 'active', 'inactive'."},
            status=status.HTTP_400_BAD_REQUEST
        )

    user.status = new_status
    user.save(update_fields=["status"])

    return Response({
        "message": f"User status updated to '{new_status}'.",
        "user_id": user.id,
        "status": user.status
    }, status=status.HTTP_200_OK)


@api_view(['PATCH'])
@permission_classes([IsAdminUser])
def update_partner_permissions(request, user_id):
    """
    PATCH /api/auth/users/<user_id>/permissions/
    {
        "permissions": [
            { "permission": "reports" },
            { "permission": "settings" }
        ]
    }
    Simplified for Managed Inventory Publisher Dashboard - no parent_gam_network needed
    """
    try:
        user = User.objects.get(id=user_id, role='partner_admin')
    except User.DoesNotExist:
        return Response({"error": "Partner not found."}, status=status.HTTP_404_NOT_FOUND)

    permission_items = request.data.get("permissions", [])
    if not isinstance(permission_items, list):
        return Response({"error": "permissions must be a list"}, status=400)

    valid_permissions = dict(PublisherPermission.PermissionChoices.choices).keys()

    new_permissions = []
    for item in permission_items:
        permission = item.get("permission") if isinstance(item, dict) else item

        if permission not in valid_permissions:
            return Response({"error": f"Invalid permission: {permission}"}, status=400)

        new_permissions.append(PublisherPermission(
            user=user,
            permission=permission
        ))

    # Delete existing permissions
    PublisherPermission.objects.filter(user=user).delete()

    # Bulk create
    PublisherPermission.objects.bulk_create(new_permissions)

    return Response({"message": "Permissions updated successfully"})


@api_view(['GET'])
@permission_classes([IsAuthenticated])  # Or AdminOnlyPermission
def get_partner_permissions(request, user_id):
    try:
        user = User.objects.get(id=user_id, role='partner_admin')
    except User.DoesNotExist:
        return Response({"error": "Partner not found"}, status=status.HTTP_404_NOT_FOUND)

    permissions = PublisherPermission.objects.filter(user=user)

    permissions_data = []
    for perm in permissions:
        permissions_data.append({"permission": perm.permission})

    return Response({
        "id": user.id,
        "company_name": user.company_name,
        "email": user.email,
        "permissions": permissions_data
    })


@api_view(['GET'])
@permission_classes([IsAdminUser])
def list_partners(request):
    """
    GET /api/auth/partners/
    List all partner users for admin dashboard
    """
    partners = User.objects.filter(role='partner_admin').order_by('-date_joined')
    serializer = PublisherListSerializer(partners, many=True)
    return Response(serializer.data, status=status.HTTP_200_OK)


class PasswordResetConfirmAPIView(APIView):
    """
    POST /api/auth/reset_password/
    {
      "uid": "MjM",
      "token": "abc...",
      "new_password": "newpass123",
      "confirm_password": "newpass123"
    }
    """
    permission_classes = [AllowAny]
    authentication_classes = []  

    def post(self, request):
        uid = request.data.get("uid")
        token = request.data.get("token")
        password = request.data.get("new_password")
        confirm = request.data.get("confirm_password")

        if not uid or not token or not password or not confirm:
            return Response({"error": "Missing fields"}, status=400)

        if password != confirm:
            return Response({"error": "Passwords do not match"}, status=400)

        try:
            uid = urlsafe_base64_decode(uid).decode()
            user = User.objects.get(pk=uid)
        except (TypeError, ValueError, OverflowError, User.DoesNotExist):
            return Response({"error": "Invalid UID"}, status=400)

        if not default_token_generator.check_token(user, token):
            return Response({"error": "Invalid or expired token"}, status=400)

        try:
            validate_password(password, user)
        except Exception as e:
            return Response({"error": e.messages}, status=400)

        user.set_password(password)
        user.save()

        # Activate pending partner admins
        if user.role == user.UserRole.PARTNER_ADMIN and user.status == StatusChoices.PENDING_APPROVAL:
            user.status = StatusChoices.ACTIVE
            user.save(update_fields=["status"])

        return Response({"message": "Password has been reset successfully."}, status=200)
    
@api_view(['DELETE'])
@permission_classes([IsAuthenticated, IsAdminUser])
def delete_partner_user(request, partner_id):
    """
    Permanently delete a partner user and all associated data.
    """
    try:
        partner = User.objects.get(id=partner_id, role='partner_admin')
        email = partner.email
        partner.delete()
        return Response({
            "success": True,
            "message": f"Partner user {email} and related records have been deleted."
        }, status=status.HTTP_200_OK)
    except User.DoesNotExist:
        return Response({
            "success": False,
            "error": "Partner user not found."
        }, status=status.HTTP_404_NOT_FOUND)


@api_view(['PUT'])
@permission_classes([IsAuthenticated])
def update_profile_view(request):
    """
    Update user profile information
    PUT /api/auth/profile/
    """
    user = request.user
    
    first_name = request.data.get('first_name', '').strip()
    last_name = request.data.get('last_name', '').strip()
    email = request.data.get('email', '').strip()
    phone_number = request.data.get('phone_number', '').strip()
    
    if not first_name or not email:
        return Response({
            'error': 'First name and email are required'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    if email != user.email:
        if User.objects.filter(email__iexact=email).exists():
            return Response({
                'error': 'Email already exists'
            }, status=status.HTTP_400_BAD_REQUEST)
        user.email = email.lower()
    
    user.first_name = first_name
    user.last_name = last_name
    user.phone_number = phone_number
    user.save(update_fields=['first_name', 'last_name', 'email', 'phone_number'])
    
    return Response({
        'success': True,
        'message': 'Profile updated successfully',
        'user': UserProfileSerializer(user).data
    }, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def change_password_view(request):
    """
    Change user password
    POST /api/auth/change-password/
    """
    user = request.user
    
    current_password = request.data.get('current_password', '')
    new_password = request.data.get('new_password', '')
    
    # Validate required fields
    if not current_password or not new_password:
        return Response({
            'error': 'Current password and new password are required'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    # Validate new password length
    if len(new_password) < 8:
        return Response({
            'error': 'New password must be at least 8 characters long'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    # Check current password
    if not user.check_password(current_password):
        return Response({
            'error': 'Current password is incorrect'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    # Set new password
    user.set_password(new_password)
    user.save()
    
    return Response({
        'success': True,
        'message': 'Password changed successfully'
    }, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsAdminUser])
def list_partners_full(request):
    """
    GET /api/auth/publishers/ - List all partner admins (kept for admin manage-partners page)
    """
    try:
        partners = User.objects.filter(role='partner_admin').prefetch_related('sites').order_by('-date_joined')
        serializer = PublisherListSerializer(partners, many=True)
        return Response(serializer.data)
    except Exception as e:
        return Response({
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['PUT'])
@permission_classes([IsAuthenticated, IsAdminUser])
def update_partner(request, user_id):
    """
    PUT /api/auth/publishers/{user_id}/ - Update partner admin details
    """
    try:
        partner = User.objects.get(id=user_id, role='partner_admin')
        
        allowed_fields = ['company_name', 'site_url', 'revenue_share_percentage', 'phone_number']
        for field in allowed_fields:
            if field in request.data:
                setattr(partner, field, request.data[field])
        
        partner.save()
        
        serializer = PublisherListSerializer(partner)
        return Response({
            'success': True,
            'message': 'Partner updated successfully',
            'data': serializer.data
        })
    except User.DoesNotExist:
        return Response({
            'error': 'Partner not found'
        }, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        return Response({
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['DELETE'])
@permission_classes([IsAuthenticated, IsAdminUser])
def delete_partner_admin_user(request, user_id):
    """
    DELETE /api/auth/publishers/{user_id}/delete/ - Delete partner admin
    """
    try:
        partner = User.objects.get(id=user_id, role='partner_admin')
        partner.delete()
        
        return Response({
            'success': True,
            'message': 'Partner deleted successfully'
        })
    except User.DoesNotExist:
        return Response({
            'error': 'Partner not found'
        }, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        return Response({
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ============================================================================
# PAYMENT DETAILS VIEWS
# ============================================================================

from .models import PaymentDetail
from .serializers import PaymentDetailSerializer, PaymentDetailListSerializer


class PaymentDetailView(APIView):
    """
    GET/POST/PUT payment details for current user
    """
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        """Get current user's payment details"""
        try:
            payment_detail = PaymentDetail.objects.get(user=request.user)
            serializer = PaymentDetailSerializer(payment_detail)
            return Response(serializer.data)
        except PaymentDetail.DoesNotExist:
            return Response({
                'detail': 'Payment details not found'
            }, status=status.HTTP_404_NOT_FOUND)
    
    def post(self, request):
        """Create payment details for current user"""
        # Check if payment details already exist
        if PaymentDetail.objects.filter(user=request.user).exists():
            return Response({
                'error': 'Payment details already exist. Use PUT to update.'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        serializer = PaymentDetailSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save(user=request.user)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    def put(self, request):
        """Update payment details for current user"""
        try:
            payment_detail = PaymentDetail.objects.get(user=request.user)
        except PaymentDetail.DoesNotExist:
            return Response({
                'error': 'Payment details not found. Use POST to create.'
            }, status=status.HTTP_404_NOT_FOUND)
        
        serializer = PaymentDetailSerializer(payment_detail, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class PaymentDetailListView(generics.ListAPIView):
    """
    GET all payment details (admin only)
    """
    permission_classes = [IsAuthenticated]
    serializer_class = PaymentDetailListSerializer
    
    def get_queryset(self):
        # Only admin can view all payment details
        if not self.request.user.is_admin_user:
            return PaymentDetail.objects.none()
        return PaymentDetail.objects.select_related('user').all()


class PaymentDetailDetailView(generics.RetrieveAPIView):
    """
    GET specific payment detail by ID (admin only)
    """
    permission_classes = [IsAuthenticated]
    serializer_class = PaymentDetailSerializer
    
    def get_queryset(self):
        # Only admin can view payment details
        if not self.request.user.is_admin_user:
            return PaymentDetail.objects.none()
        return PaymentDetail.objects.select_related('user').all()


class SiteListView(generics.ListAPIView):
    """
    GET all sites
    - Admin: sees all sites
    - Partner admin: sees only their own sites
    
    Also creates Site records for existing partner admins who don't have sites yet
    """
    permission_classes = [IsAuthenticated]
    serializer_class = SiteSerializer
    
    def get_queryset(self):
        from .models import Site
        
        if self.request.user.is_admin_user:
            publishers_with_url = User.objects.filter(
                role=User.UserRole.PARTNER_ADMIN,
                site_url__isnull=False
            ).exclude(site_url='')
        else:
            publishers_with_url = User.objects.filter(
                id=self.request.user.id,
                role=User.UserRole.PARTNER_ADMIN,
                site_url__isnull=False
            ).exclude(site_url='')
        
        for publisher in publishers_with_url:
            default_status = Site.GamStatus.GETTING_READY
            Site.objects.get_or_create(
                publisher=publisher,
                url=publisher.site_url,
                defaults={
                    'gam_status': default_status,
                    'ads_txt_status': Site.AdsTxtStatus.MISSING,
                }
            )
        
        # Return queryset
        if self.request.user.is_admin_user:
            # Admin sees all sites
            return Site.objects.select_related('publisher').all()
        else:
            # Publisher sees only their own sites
            return Site.objects.filter(publisher=self.request.user).select_related('publisher')


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def sync_sites_status_view(request):
    """
    Sync site statuses from GAM for all sites
    Admin only
    """
    if not request.user.is_admin_user:
        return Response(
            {'error': 'Only admin users can sync site statuses'},
            status=status.HTTP_403_FORBIDDEN
        )
    
    try:
        # Sync all sites status from GAM
        result = GAMClientService.sync_all_sites_status_from_gam()
        
        if not result.get('success'):
            return Response({
                'success': False,
                'error': result.get('error', 'Failed to sync site statuses')
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
        return Response({
            'success': True,
            'message': f'Synced {result.get("synced", 0)} sites from GAM',
            'synced': result.get('synced', 0),
            'errors': result.get('errors', 0),
            'total': result.get('total', 0)
        })
        
    except Exception as e:
        logger.error(f"❌ Error syncing site statuses: {str(e)}")
        return Response({
            'success': False,
            'error': f'Failed to sync site statuses: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)





# =============================================================================
# SUB-PUBLISHER MANAGEMENT
# =============================================================================

from .permissions import IsPartnerAdminOrAdmin, IsSubPublisherOwnerOrAdmin
from .serializers import (
    SubPublisherListSerializer,
    SubPublisherCreateSerializer,
    SubPublisherUpdateSerializer,
    TrackingAssignmentSerializer,
    TrackingAssignmentCreateSerializer,
    SubdomainSerializer,
    TutorialSerializer,
    TutorialListSerializer,
)
from .models import TrackingAssignment, Subdomain, Tutorial


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated, IsPartnerAdminOrAdmin])
def sub_publisher_list_create(request):
    """
    GET  — list sub-publishers owned by the requesting partner_admin (admin sees all).
    POST — create a new sub-publisher under the requesting partner_admin.
    """
    if request.method == 'GET':
        qs = User.objects.filter(role=User.UserRole.SUB_PUBLISHER).select_related('tracking_assignment')
        if request.user.role == 'partner_admin':
            qs = qs.filter(parent_publisher=request.user)
        serializer = SubPublisherListSerializer(qs, many=True)
        return Response(serializer.data)

    serializer = SubPublisherCreateSerializer(data=request.data, context={'request': request})
    serializer.is_valid(raise_exception=True)
    sub_pub = serializer.save()
    return Response(
        SubPublisherListSerializer(sub_pub).data,
        status=status.HTTP_201_CREATED,
    )


@api_view(['GET', 'PUT', 'DELETE'])
@permission_classes([IsAuthenticated])
def sub_publisher_detail(request, sub_id):
    """
    GET    — detail view (partner_admin sees own children, admin sees all, sub_pub sees self).
    PUT    — update sub-publisher profile/fee.
    DELETE — soft-delete (set status to SUSPENDED).
    """
    try:
        sub_pub = User.objects.select_related('tracking_assignment').get(
            id=sub_id, role=User.UserRole.SUB_PUBLISHER,
        )
    except User.DoesNotExist:
        return Response({'error': 'Sub-publisher not found.'}, status=status.HTTP_404_NOT_FOUND)

    perm = IsSubPublisherOwnerOrAdmin()
    if not perm.has_object_permission(request, None, sub_pub):
        return Response({'error': 'Permission denied.'}, status=status.HTTP_403_FORBIDDEN)

    if request.method == 'GET':
        return Response(SubPublisherListSerializer(sub_pub).data)

    if request.method == 'DELETE':
        sub_pub.status = StatusChoices.SUSPENDED
        sub_pub.save(update_fields=['status'])
        return Response({'message': 'Sub-publisher suspended.'})

    serializer = SubPublisherUpdateSerializer(sub_pub, data=request.data, partial=True)
    serializer.is_valid(raise_exception=True)
    serializer.save()
    return Response(SubPublisherListSerializer(sub_pub).data)


@api_view(['GET', 'POST', 'PUT'])
@permission_classes([IsAuthenticated, IsPartnerAdminOrAdmin])
def sub_publisher_tracking(request, sub_id):
    """
    GET  — view current tracking assignment (subdomain).
    POST — create tracking assignment (first time).
    PUT  — update tracking assignment subdomain.
    """
    try:
        sub_pub = User.objects.get(id=sub_id, role=User.UserRole.SUB_PUBLISHER)
    except User.DoesNotExist:
        return Response({'error': 'Sub-publisher not found.'}, status=status.HTTP_404_NOT_FOUND)

    if request.user.role == 'partner_admin' and sub_pub.parent_publisher_id != request.user.id:
        return Response({'error': 'Permission denied.'}, status=status.HTTP_403_FORBIDDEN)

    if request.method == 'GET':
        try:
            ta = sub_pub.tracking_assignment
            return Response(TrackingAssignmentSerializer(ta).data)
        except TrackingAssignment.DoesNotExist:
            return Response({'tracking': None})

    ser = TrackingAssignmentCreateSerializer(data=request.data)
    ser.is_valid(raise_exception=True)
    data = ser.validated_data

    if request.method == 'POST':
        if hasattr(sub_pub, 'tracking_assignment'):
            try:
                sub_pub.tracking_assignment
                return Response(
                    {'error': 'Tracking assignment already exists. Use PUT to update.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            except TrackingAssignment.DoesNotExist:
                pass

        ta = TrackingAssignment.objects.create(
            sub_publisher=sub_pub,
            partner_admin=request.user,
            subdomain=data['subdomain'],
            notes=data.get('notes', ''),
        )
        return Response(TrackingAssignmentSerializer(ta).data, status=status.HTTP_201_CREATED)

    # PUT
    try:
        ta = sub_pub.tracking_assignment
    except TrackingAssignment.DoesNotExist:
        return Response({'error': 'No tracking assignment to update. Use POST.'}, status=status.HTTP_404_NOT_FOUND)

    ta.subdomain = data['subdomain']
    ta.notes = data.get('notes', ta.notes)
    ta.save()
    return Response(TrackingAssignmentSerializer(ta).data)


@api_view(['GET', 'POST', 'DELETE'])
@permission_classes([IsAuthenticated, IsPartnerAdminOrAdmin])
def subdomain_list_create_delete(request, subdomain_id=None):
    """
    GET    — list subdomains for the partner_admin.
    POST   — create a new subdomain.
    DELETE — delete a subdomain by ID (passed as URL param).
    """
    if request.method == 'DELETE' and subdomain_id:
        try:
            sd = Subdomain.objects.get(id=subdomain_id)
        except Subdomain.DoesNotExist:
            return Response({'error': 'Subdomain not found.'}, status=status.HTTP_404_NOT_FOUND)
        if request.user.role == 'partner_admin' and sd.partner_admin_id != request.user.id:
            return Response({'error': 'Permission denied.'}, status=status.HTTP_403_FORBIDDEN)
        sd.delete()
        return Response({'message': 'Subdomain deleted.'})

    if request.method == 'GET':
        qs = Subdomain.objects.select_related('assigned_to')
        if request.user.role == 'partner_admin':
            qs = qs.filter(partner_admin=request.user)
        return Response(SubdomainSerializer(qs, many=True).data)

    serializer = SubdomainSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    serializer.save(partner_admin=request.user)
    return Response(serializer.data, status=status.HTTP_201_CREATED)


# =============================================================================
# TUTORIALS API
# =============================================================================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def tutorial_list(request):
    """List tutorials filtered by user role."""
    qs = Tutorial.objects.filter(is_published=True)
    user_role = request.user.role
    filtered = []
    for t in qs:
        if not t.target_roles or user_role in t.target_roles:
            filtered.append(t)
    return Response(TutorialListSerializer(filtered, many=True).data)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def tutorial_detail(request, slug):
    """Get single tutorial by slug."""
    try:
        t = Tutorial.objects.get(slug=slug, is_published=True)
    except Tutorial.DoesNotExist:
        return Response({'error': 'Tutorial not found.'}, status=status.HTTP_404_NOT_FOUND)
    user_role = request.user.role
    if t.target_roles and user_role not in t.target_roles:
        return Response({'error': 'Not available for your role.'}, status=status.HTTP_403_FORBIDDEN)
    return Response(TutorialSerializer(t).data)


@api_view(['POST'])
@permission_classes([IsAuthenticated, IsAdminUser])
def tutorial_create(request):
    """Admin-only: create a tutorial."""
    serializer = TutorialSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    serializer.save()
    return Response(serializer.data, status=status.HTTP_201_CREATED)


# ---------------------------------------------------------------------------
# GAM Credential Management Views
# ---------------------------------------------------------------------------
from .serializers import GAMCredentialSerializer, GAMConnectSerializer


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsPartnerAdminOrAdmin])
def gam_status(request):
    """Return GAM connection status for the current partner admin."""
    try:
        cred = GAMCredential.objects.get(partner_admin=request.user)
        return Response(GAMCredentialSerializer(cred).data)
    except GAMCredential.DoesNotExist:
        return Response({
            'is_connected': False,
            'service_account_email': getattr(settings, 'GAM_SERVICE_ACCOUNT_EMAIL', ''),
        })


@api_view(['POST'])
@permission_classes([IsAuthenticated, IsPartnerAdminOrAdmin])
def gam_connect(request):
    """
    Connect partner's GAM account via service account method.
    Partner must add our service email as admin in their GAM first.
    """
    serializer = GAMConnectSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    network_code = serializer.validated_data['network_code']
    auth_method = serializer.validated_data.get('auth_method', GAMCredential.AuthMethod.SERVICE_ACCOUNT)

    cred, created = GAMCredential.objects.update_or_create(
        partner_admin=request.user,
        defaults={
            'auth_method': auth_method,
            'network_code': network_code,
            'is_connected': False,
            'connection_error': '',
        },
    )

    test_result = GAMClientService.test_connection_for_partner(request.user)
    if test_result['success']:
        cred.is_connected = True
        cred.connection_error = ''
        cred.last_synced_at = timezone.now()
        cred.save(update_fields=['is_connected', 'connection_error', 'last_synced_at'])
        return Response({
            'success': True,
            'message': 'GAM account connected successfully.',
            'credential': GAMCredentialSerializer(cred).data,
            'network_info': test_result,
        })
    else:
        cred.connection_error = test_result.get('error', 'Connection test failed.')
        cred.save(update_fields=['connection_error'])
        return Response({
            'success': False,
            'error': test_result.get('error', 'Connection test failed.'),
            'credential': GAMCredentialSerializer(cred).data,
        }, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@permission_classes([IsAuthenticated, IsPartnerAdminOrAdmin])
def gam_test(request):
    """Test the current GAM connection for the partner admin."""
    try:
        cred = GAMCredential.objects.get(partner_admin=request.user)
    except GAMCredential.DoesNotExist:
        return Response(
            {'error': 'No GAM credentials configured. Connect first.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    test_result = GAMClientService.test_connection_for_partner(request.user)
    if test_result['success']:
        cred.is_connected = True
        cred.connection_error = ''
        cred.last_synced_at = timezone.now()
        cred.save(update_fields=['is_connected', 'connection_error', 'last_synced_at'])
    else:
        cred.is_connected = False
        cred.connection_error = test_result.get('error', 'Test failed.')
        cred.save(update_fields=['is_connected', 'connection_error'])

    return Response({
        'success': test_result['success'],
        **test_result,
        'credential': GAMCredentialSerializer(cred).data,
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated, IsPartnerAdminOrAdmin])
def gam_disconnect(request):
    """Disconnect GAM credentials for the current partner admin."""
    deleted, _ = GAMCredential.objects.filter(partner_admin=request.user).delete()
    if deleted:
        GAMClientService.clear_partner_cache(request.user.id)
        return Response({'success': True, 'message': 'GAM account disconnected.'})
    return Response(
        {'error': 'No GAM credentials to disconnect.'},
        status=status.HTTP_400_BAD_REQUEST,
    )


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsPartnerAdminOrAdmin])
def gam_oauth_init(request):
    """
    Start OAuth 2.0 flow — returns the Google consent URL.
    Partner clicks the URL, authenticates, and Google redirects back with an auth code.
    """
    from google_auth_oauthlib.flow import Flow

    client_config = {
        'web': {
            'client_id': getattr(settings, 'GAM_OAUTH_CLIENT_ID', ''),
            'client_secret': getattr(settings, 'GAM_OAUTH_CLIENT_SECRET', ''),
            'auth_uri': 'https://accounts.google.com/o/oauth2/auth',
            'token_uri': 'https://oauth2.googleapis.com/token',
        }
    }

    redirect_uri = getattr(settings, 'GAM_OAUTH_REDIRECT_URI', '')
    if not client_config['web']['client_id'] or not redirect_uri:
        return Response(
            {'error': 'OAuth 2.0 is not configured on this server.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    flow = Flow.from_client_config(
        client_config,
        scopes=['https://www.googleapis.com/auth/admanager'],
        redirect_uri=redirect_uri,
    )

    auth_url, state = flow.authorization_url(
        access_type='offline',
        include_granted_scopes='true',
        prompt='consent',
        state=str(request.user.id),
    )

    return Response({'auth_url': auth_url, 'state': state})


@api_view(['POST'])
@permission_classes([IsAuthenticated, IsPartnerAdminOrAdmin])
def gam_oauth_callback(request):
    """
    Handle OAuth 2.0 callback — exchange auth code for refresh token.
    Expects: { "code": "...", "network_code": "..." }
    """
    from google_auth_oauthlib.flow import Flow

    code = request.data.get('code')
    network_code = request.data.get('network_code', '')
    if not code:
        return Response({'error': 'Authorization code is required.'}, status=status.HTTP_400_BAD_REQUEST)
    if not network_code:
        return Response({'error': 'Network code is required.'}, status=status.HTTP_400_BAD_REQUEST)

    client_config = {
        'web': {
            'client_id': getattr(settings, 'GAM_OAUTH_CLIENT_ID', ''),
            'client_secret': getattr(settings, 'GAM_OAUTH_CLIENT_SECRET', ''),
            'auth_uri': 'https://accounts.google.com/o/oauth2/auth',
            'token_uri': 'https://oauth2.googleapis.com/token',
        }
    }

    redirect_uri = getattr(settings, 'GAM_OAUTH_REDIRECT_URI', '')

    try:
        flow = Flow.from_client_config(
            client_config,
            scopes=['https://www.googleapis.com/auth/admanager'],
            redirect_uri=redirect_uri,
        )
        flow.fetch_token(code=code)
        credentials = flow.credentials

        cred, _ = GAMCredential.objects.update_or_create(
            partner_admin=request.user,
            defaults={
                'auth_method': GAMCredential.AuthMethod.OAUTH2,
                'network_code': network_code,
                'oauth_refresh_token': credentials.refresh_token or '',
                'oauth_client_id': client_config['web']['client_id'],
                'is_connected': True,
                'connection_error': '',
                'last_synced_at': timezone.now(),
            },
        )

        test_result = GAMClientService.test_connection_for_partner(request.user)
        if not test_result['success']:
            cred.is_connected = False
            cred.connection_error = test_result.get('error', 'Post-OAuth test failed.')
            cred.save(update_fields=['is_connected', 'connection_error'])
            return Response({
                'success': False,
                'error': test_result.get('error', 'Connected but test failed.'),
            }, status=status.HTTP_400_BAD_REQUEST)

        return Response({
            'success': True,
            'message': 'OAuth 2.0 connected successfully.',
            'credential': GAMCredentialSerializer(cred).data,
        })

    except Exception as e:
        logger.error(f"OAuth callback failed for {request.user.email}: {e}")
        return Response(
            {'error': f'OAuth authentication failed: {str(e)}'},
            status=status.HTTP_400_BAD_REQUEST,
        )