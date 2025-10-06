"""
Clean authentication views for API-only endpoints
No CSRF decorators needed - using JWT authentication only
"""
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
from core.models import StatusChoices
from gam_accounts.models import GAMNetwork

from .models import PartnerPermission, User
from .serializers import (
    PartnerListSerializer,
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
            request.user.role == 'ADMIN'
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
    serializer = UserLoginSerializer(
        data=request.data,
        context={'request': request}
    )
    
    if serializer.is_valid():
        user = serializer.validated_data['user']
        
        # Update last login IP
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        
        user.last_login_ip = ip
        user.save(update_fields=['last_login_ip'])
        
        # Generate JWT tokens
        refresh = RefreshToken.for_user(user)
        
        return Response({
            'message': 'Login successful',
            'user': UserProfileSerializer(user).data,
            'tokens': {
                'refresh': str(refresh),
                'access': str(refresh.access_token),
            }
        }, status=status.HTTP_200_OK)
    
    return Response(
        serializer.errors,
        status=status.HTTP_400_BAD_REQUEST
    )


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
        print(f"Logout error: {error_msg}")
        
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
    from .rbac_service import RBACService
    
    user = request.user
    
    # Get effective permissions using new RBAC service
    effective_permissions = RBACService.get_effective_permissions(user)
    
    # Get user scope
    scope = RBACService.get_user_scope(user)
    
    # Convert permissions to frontend-compatible format
    permissions = {}
    for perm in effective_permissions:
        permissions[perm] = True
    
    # Get assigned accounts count
    assigned_count = 0
    if scope['publisher_ids'] is not None:
        assigned_count = len(scope['publisher_ids'])
    else:
        # Admin sees all
        from gam_accounts.models import MCMInvitation
        assigned_count = MCMInvitation.objects.count()
    
    # Get parent network info for parent users
    parent_network_info = None
    if user.role == 'parent' and scope['parent_network_id']:
        from gam_accounts.models import GAMNetwork
        try:
            parent_network = GAMNetwork.objects.get(id=scope['parent_network_id'])
            parent_network_info = {
                'id': parent_network.id,
                'name': parent_network.network_name,
                'code': parent_network.network_code,
            }
        except GAMNetwork.DoesNotExist:
            pass
    
    return Response({
        'user_id': user.id,
        'email': user.email,
        'role': user.role,
        'status': user.status,
        'is_admin': user.role == 'ADMIN',
        'permissions': permissions,
        'assigned_accounts_count': assigned_count,
        'parent_network': parent_network_info,
        'can_modify_gam_status': user.role == 'ADMIN',
        'permissions_version': user.permissions_version,
        'effective_permissions': list(effective_permissions),
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
            'partner_users': User.objects.filter(role='partner').count(),
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
            from gam_accounts.models import GAMNetwork, MCMInvitation
            parent_network = GAMNetwork.objects.get(id=parent_network_id)
            child_networks = MCMInvitation.objects.filter(parent_network=parent_network)
            
            dashboard_data['network_stats'] = {
                'network_name': parent_network.network_name,
                'total_child_networks': child_networks.count(),
                'active_child_networks': child_networks.filter(status='active').count(),
                'total_partners': User.objects.filter(role='partner').count(),  # All partners for now
            }
    elif user.role.upper() == 'PARTNER':
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
        if user.role == user.UserRole.PARTNER and user.status == StatusChoices.PENDING_APPROVAL:
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
        user = User.objects.get(id=user_id, role='partner')
    except User.DoesNotExist:
        return Response({"error": "Partner not found."}, status=status.HTTP_404_NOT_FOUND)

    permission_items = request.data.get("permissions", [])
    if not isinstance(permission_items, list):
        return Response({"error": "permissions must be a list"}, status=400)

    valid_permissions = dict(PartnerPermission.PermissionChoices.choices).keys()

    new_permissions = []
    for item in permission_items:
        permission = item.get("permission")
        parent_gam_id = item.get("parent_gam_network")

        if permission not in valid_permissions:
            return Response({"error": f"Invalid permission: {permission}"}, status=400)

        if permission == 'mcm_invites':
            if not parent_gam_id:
                return Response({"error": "parent_gam_network is required for mcm_invites"}, status=400)
            try:
                parent_network = GAMNetwork.objects.get(id=parent_gam_id, network_type='parent')
            except GAMNetwork.DoesNotExist:
                return Response({"error": f"Invalid parent GAM network ID: {parent_gam_id}"}, status=400)
        else:
            parent_network = None

        new_permissions.append(PartnerPermission(
            user=user,
            permission=permission,
            parent_gam_network=parent_network
        ))

    # Delete existing permissions
    PartnerPermission.objects.filter(user=user).delete()

    # Bulk create
    PartnerPermission.objects.bulk_create(new_permissions)

    return Response({"message": "Permissions updated successfully"})


@api_view(['GET'])
@permission_classes([IsAuthenticated])  # Or AdminOnlyPermission
def get_partner_permissions(request, user_id):
    try:
        user = User.objects.get(id=user_id, role='partner')
    except User.DoesNotExist:
        return Response({"error": "Partner not found"}, status=status.HTTP_404_NOT_FOUND)

    permissions = PartnerPermission.objects.filter(user=user)

    permissions_data = []
    for perm in permissions:
        entry = {"permission": perm.permission}
        if perm.permission == PartnerPermission.PermissionChoices.MCM_INVITES and perm.parent_gam_network:
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
    partners = User.objects.filter(role='partner').order_by('-date_joined')
    serializer = PartnerListSerializer(partners, many=True)
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

        # Activate pending partners
        if user.role == user.UserRole.PARTNER and user.status == StatusChoices.PENDING_APPROVAL:
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
        partner = User.objects.get(id=partner_id, role='partner')  # Optional: filter by role
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