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

from .models import PublisherPermission, User

logger = logging.getLogger(__name__)
DEBUG = settings.DEBUG
from .permissions import load_publisher_permissions
from .serializers import (
    PublisherListSerializer,
    UserRegistrationSerializer,
    UserLoginSerializer,
    UserProfileSerializer,
    UserRoleUpdateSerializer,
    ChangePasswordSerializer
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
def public_signup_view(request):
    """
    Public signup endpoint for new publishers
    POST /api/auth/public-signup/
    
    Body:
    {
        "name": "John Doe",
        "phone": "+1234567890",
        "email": "publisher@example.com",
        "site_link": "https://example.com"
    }
    
    This endpoint:
    1. Creates a new publisher user
    2. Sends MCM invitation via Google AdManager API
    3. Sends welcome email with password reset link
    """
    from .serializers import PublicSignupSerializer
    
    serializer = PublicSignupSerializer(data=request.data)
    
    if serializer.is_valid():
        try:
            user = serializer.save()
            
            return Response({
                'success': True,
                'message': 'Signup successful! Please check your email to set your password and accept the GAM invitation.',
                'user': {
                    'id': user.id,
                    'email': user.email,
                    'name': user.get_full_name()
                }
            }, status=status.HTTP_201_CREATED)
            
        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            logger.error(f"❌ Public signup error: {error_details}")
            
            return Response({
                'success': False,
                'error': f'Signup failed: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    return Response({
        'success': False,
        'errors': serializer.errors
    }, status=status.HTTP_400_BAD_REQUEST)


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
        # Always return error detail in production for debugging
        return Response({
            'error': 'An error occurred during login. Please try again.',
            'detail': str(e)
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
    from .rbac_service import RBACService
    
    user = request.user
    
    # Get user scope for data filtering
    scope = RBACService.get_user_scope(user)
    
    # Basic dashboard data
    dashboard_data = {
        'message': f'Welcome to GAM Platform, {user.get_full_name()}!',
        'user': UserProfileSerializer(user).data,
        'user_role': user.role,
        'is_admin': user.role.upper() == 'ADMIN',
    }
    
    # Add role-specific data
    if user.role.upper() == 'ADMIN':
        # Admin sees all platform data
        dashboard_data['platform_stats'] = {
            'total_users': User.objects.count(),
            'active_users': User.objects.filter(status='active').count(),
            'admin_users': User.objects.filter(role='admin').count(),
            'publisher_users': User.objects.filter(role='publisher').count(),
        }
        dashboard_data['admin_features'] = {
            'can_manage_all_networks': True,
            'can_send_mcm_invitations': True,
            'can_manage_users': True,
            'can_configure_alerts': True,
        }
    elif user.role.upper() == 'PARENT':
        # Parent sees data for their network only
        parent_network_id = scope.get('parent_network_id')
        if parent_network_id:
            # Simplified for managed inventory - no parent network logic
            child_networks = []
            
            dashboard_data['network_stats'] = {
                'network_name': 'Managed Inventory Network',
                'total_child_networks': 0,
                'active_child_networks': 0,
                'total_publishers': User.objects.filter(role='publisher').count(),  # All publishers for now
            }
    elif user.role.upper() == 'PUBLISHER':
        # Partner sees only their assigned data
        publisher_ids = scope.get('publisher_ids', [])
        assigned_count = len(publisher_ids) if publisher_ids is not None else 0
        effective_permissions = RBACService.get_effective_permissions(user)
        dashboard_data['partner_stats'] = {
            'assigned_accounts': assigned_count,
            'accessible_reports': 1 if 'reports' in effective_permissions else 0,
            'managed_websites': 0,  # Will be populated from actual assignments
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
        # Publishers are activated automatically
        if user.role == user.UserRole.PUBLISHER and user.status == StatusChoices.PENDING_APPROVAL:
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
            { "permission": "manage_mcm_invites", "parent_gam_network": 1 },
            { "permission": "verify_accounts" }
        ]
    }
    """
    try:
        user = User.objects.get(id=user_id, role='publisher')
    except User.DoesNotExist:
        return Response({"error": "Partner not found."}, status=status.HTTP_404_NOT_FOUND)

    permission_items = request.data.get("permissions", [])
    if not isinstance(permission_items, list):
        return Response({"error": "permissions must be a list"}, status=400)

    valid_permissions = dict(PublisherPermission.PermissionChoices.choices).keys()

    new_permissions = []
    for item in permission_items:
        permission = item.get("permission")
        parent_gam_id = item.get("parent_gam_network")

        if permission not in valid_permissions:
            return Response({"error": f"Invalid permission: {permission}"}, status=400)

        # Simplified for managed inventory - no GAMNetwork model needed
        # MCM invitations are handled via GAM API directly
        if permission == 'mcm_invites':
            # For managed inventory, we don't need parent_gam_network
            # The system uses the parent network from settings
            pass

        new_permissions.append(PublisherPermission(
            user=user,
            permission=permission,
            parent_gam_network=parent_network
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
        user = User.objects.get(id=user_id, role='publisher')
    except User.DoesNotExist:
        return Response({"error": "Partner not found"}, status=status.HTTP_404_NOT_FOUND)

    permissions = PublisherPermission.objects.filter(user=user)

    permissions_data = []
    for perm in permissions:
        entry = {"permission": perm.permission}
        if perm.permission == PublisherPermission.PermissionChoices.MANAGED_ACCOUNTS and perm.parent_gam_network:
            entry["parent_gam_network"] = {
                "id": perm.parent_gam_network.id,
                "network_code": perm.parent_gam_network.network_code,
                "network_name": perm.parent_gam_network.network_name
            }
        permissions_data.append(entry)

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
    partners = User.objects.filter(role='publisher').order_by('-date_joined')
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

        # Activate pending publishers
        if user.role == user.UserRole.PUBLISHER and user.status == StatusChoices.PENDING_APPROVAL:
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
        partner = User.objects.get(id=partner_id, role='publisher')  # Optional: filter by role
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
    
    # Get data from request
    full_name = request.data.get('full_name', '')
    email = request.data.get('email', '')
    phone = request.data.get('phone', '')
    
    # Validate required fields
    if not full_name or not email:
        return Response({
            'error': 'Full name and email are required'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    # Check if email is being changed and if it's already taken
    if email != user.email:
        if User.objects.filter(email=email).exists():
            return Response({
                'error': 'Email already exists'
            }, status=status.HTTP_400_BAD_REQUEST)
        user.email = email
    
    # Update user fields
    user.full_name = full_name
    user.phone = phone
    user.save()
    
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


# Simplified publisher management functions for managed inventory

@api_view(['GET'])
@permission_classes([IsAuthenticated, IsAdminUser])
def list_publishers(request):
    """
    GET /api/auth/publishers/ - List all publishers
    """
    try:
        publishers = User.objects.filter(role='publisher').order_by('-date_joined')
        serializer = PublisherListSerializer(publishers, many=True)
        return Response(serializer.data)
    except Exception as e:
        return Response({
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['PUT'])
@permission_classes([IsAuthenticated, IsAdminUser])
def update_publisher(request, user_id):
    """
    PUT /api/auth/publishers/{user_id}/ - Update publisher details
    """
    try:
        publisher = User.objects.get(id=user_id, role='publisher')
        
        # Update allowed fields
        allowed_fields = ['company_name', 'site_url', 'network_id', 'revenue_share_percentage', 'phone_number']
        for field in allowed_fields:
            if field in request.data:
                setattr(publisher, field, request.data[field])
        
        publisher.save()
        
        serializer = PublisherListSerializer(publisher)
        return Response({
            'success': True,
            'message': 'Publisher updated successfully',
            'data': serializer.data
        })
    except User.DoesNotExist:
        return Response({
            'error': 'Publisher not found'
        }, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        return Response({
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsAdminUser])
def get_publisher_permissions(request, user_id):
    """
    GET /api/auth/publishers/{user_id}/permissions/ - Get publisher permissions
    """
    try:
        publisher = User.objects.get(id=user_id, role='publisher')
        permissions = PublisherPermission.objects.filter(user=publisher)
        permission_list = [p.permission for p in permissions]
        
        return Response({
            'user_id': publisher.id,
            'email': publisher.email,
            'permissions': permission_list
        })
    except User.DoesNotExist:
        return Response({
            'error': 'Publisher not found'
        }, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        return Response({
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['PATCH'])
@permission_classes([IsAuthenticated, IsAdminUser])
def update_publisher_permissions(request, user_id):
    """
    PATCH /api/auth/users/{user_id}/permissions/ - Update publisher permissions
    """
    try:
        publisher = User.objects.get(id=user_id, role='publisher')
        permissions = request.data.get('permissions', [])
        
        # Clear existing permissions
        PublisherPermission.objects.filter(user=publisher).delete()
        
        # Add new permissions
        for permission in permissions:
            PublisherPermission.objects.create(
                user=publisher,
                permission=permission
            )
        
        return Response({
            'success': True,
            'message': 'Permissions updated successfully'
        })
    except User.DoesNotExist:
        return Response({
            'error': 'Publisher not found'
        }, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        return Response({
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['DELETE'])
@permission_classes([IsAuthenticated, IsAdminUser])
def delete_publisher_user(request, user_id):
    """
    DELETE /api/auth/publishers/{user_id}/delete/ - Delete publisher
    """
    try:
        publisher = User.objects.get(id=user_id, role='publisher')
        publisher.delete()
        
        return Response({
            'success': True,
            'message': 'Publisher deleted successfully'
        })
    except User.DoesNotExist:
        return Response({
            'error': 'Publisher not found'
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
    GET/POST/PUT payment details for current user (publishers only)
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