"""
Publisher Permission System
Provides helper functions and mixins for role-based access control
"""

from functools import wraps
from django.core.cache import cache
from django.db.models import Q
from rest_framework import permissions
from rest_framework.response import Response
from rest_framework import status as http_status
import logging

logger = logging.getLogger(__name__)


class PermissionType:
    """Permission type constants"""
    ACCESS_REPORTS = 'access_reports'
    
    ALL_PERMISSIONS = [
        ACCESS_REPORTS,
    ]
    
    LABELS = {
        ACCESS_REPORTS: 'Access Reports',
    }


def get_cache_key(user_id):
    """Get cache key for user permissions"""
    return f'publisher_permissions_{user_id}'


def load_publisher_permissions(user):
    """
    Load publisher permissions from database with caching
    
    Args:
        user: User object
    
    Returns:
        dict: Permission toggles (e.g., {'access_reports': True, ...})
    """
    if not user or not user.is_authenticated:
        return {}
    
    # Admin users have all permissions
    if user.is_staff or user.is_superuser or user.role == 'admin':
        return {perm: True for perm in PermissionType.ALL_PERMISSIONS}
    
    # Parent users have most permissions except manage publishers and settings
    # They have implicit access based on their parent network
    if user.role == 'parent':
        return {
            'access_reports': True,
        }
    
    # Try cache first
    cache_key = get_cache_key(user.id)
    cached_perms = cache.get(cache_key)
    
    if cached_perms is not None:
        return cached_perms
    
    # Load from database
    from .models import PublisherPermission
    
    permissions = {}
    publisher_perms = PublisherPermission.objects.filter(user=user)
    
    for perm_obj in publisher_perms:
        permissions[perm_obj.permission] = True
    
    # Set defaults for missing permissions
    for perm in PermissionType.ALL_PERMISSIONS:
        if perm not in permissions:
            permissions[perm] = False
    
    # Cache for 5 minutes
    cache.set(cache_key, permissions, 300)
    
    return permissions


def has_publisher_permission(user, permission_type):
    """
    Check if user has a specific permission
    
    Args:
        user: User object
        permission_type: Permission type from PermissionType class
    
    Returns:
        bool: True if user has permission
    """
    if not user or not user.is_authenticated:
        return False
    
    # Admin users always have permission
    if user.is_staff or user.is_superuser or user.role == 'admin':
        return True
    
    permissions = load_publisher_permissions(user)
    return permissions.get(permission_type, False)


def clear_permission_cache(user_id):
    """Clear cached permissions for a user"""
    cache_key = get_cache_key(user_id)
    cache.delete(cache_key)
    logger.info(f"Cleared permission cache for user {user_id}")


def require_permission(permission_type):
    """
    Decorator to require a specific permission for a view
    
    Usage:
        @require_permission(PermissionType.ACCESS_REPORTS)
        def my_view(request):
            ...
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapped_view(request, *args, **kwargs):
            if not has_publisher_permission(request.user, permission_type):
                return Response(
                    {
                        'error': 'Permission denied',
                        'detail': f'You do not have permission to {PermissionType.LABELS.get(permission_type, permission_type)}',
                        'required_permission': permission_type
                    },
                    status=http_status.HTTP_403_FORBIDDEN
                )
            return view_func(request, *args, **kwargs)
        return wrapped_view
    return decorator


class HasPublisherPermission(permissions.BasePermission):
    """
    Custom permission class for DRF views
    
    Usage:
        class MyView(APIView):
            permission_classes = [IsAuthenticated, HasPartnerPermission]
            required_permission = PermissionType.ACCESS_REPORTS
    """
    
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        
        # Admin users always have permission
        if request.user.is_staff or request.user.is_superuser or request.user.role == 'admin':
            return True
        
        # Get required permission from view
        required_permission = getattr(view, 'required_permission', None)
        
        if not required_permission:
            # If no permission specified, allow access
            return True
        
        return has_publisher_permission(request.user, required_permission)


class PublisherQuerysetMixin:
    """
    Mixin to filter querysets based on publisher assignments
    Automatically limits publishers to their assigned child accounts
    """
    
    def get_queryset(self):
        """Override to filter by publisher assignments"""
        # Try to get queryset from parent class
        try:
            queryset = super().get_queryset()
        except (AttributeError, AssertionError):
            # If parent doesn't have queryset, build it from scratch
            # This handles views that don't define a queryset attribute
            from gam_accounts.models import MCMInvitation
            queryset = MCMInvitation.objects.all()
        
        # Admin users see everything
        if self.request.user.is_staff or self.request.user.is_superuser or self.request.user.role == 'admin':
            return queryset
        
        # Publisher users only see assigned accounts
        if self.request.user.role == 'publisher':
            from gam_accounts.models import AssignedPublisherChildAccount
            
            # Get assigned invitation IDs
            assigned_ids = AssignedPublisherChildAccount.objects.filter(
                publisher=self.request.user
            ).values_list('invitation_id', flat=True)
            
            # Filter queryset by assigned invitations
            # This works for models that have 'invitation' FK
            if hasattr(queryset.model, 'invitation'):
                queryset = queryset.filter(invitation_id__in=list(assigned_ids))
            # For models with 'child_network_code'
            elif hasattr(queryset.model, 'child_network_code'):
                from gam_accounts.models import MCMInvitation
                assigned_codes = MCMInvitation.objects.filter(
                    id__in=list(assigned_ids)
                ).values_list('child_network_code', flat=True)
                queryset = queryset.filter(child_network_code__in=list(assigned_codes))
            # For MCMInvitation model itself
            elif queryset.model.__name__ == 'MCMInvitation':
                queryset = queryset.filter(id__in=list(assigned_ids))
        
        return queryset


def get_assigned_child_network_codes(user):
    """
    Get list of child network codes assigned to a publisher
    
    Args:
        user: User object
    
    Returns:
        list: List of child network codes
    """
    if not user or not user.is_authenticated:
        return []
    
    # Admin users have access to all
    if user.is_staff or user.is_superuser or user.role == 'admin':
        return None  # None means "all"
    
    from gam_accounts.models import AssignedPublisherChildAccount, MCMInvitation
    
    # Get assigned invitation IDs
    assigned_ids = AssignedPublisherChildAccount.objects.filter(
        publisher=user
    ).values_list('invitation_id', flat=True)
    
    # Get network codes
    network_codes = MCMInvitation.objects.filter(
        id__in=list(assigned_ids)
    ).values_list('child_network_code', flat=True)
    
    return list(network_codes)


def can_modify_gam_status(user):
    """
    Check if user can modify GAM status
    Only admin users can change GAM status
    
    Args:
        user: User object
    
    Returns:
        bool: True if user can modify GAM status
    """
    if not user or not user.is_authenticated:
        return False
    
    # Only admins can modify GAM status
    return user.is_staff or user.is_superuser or user.role == 'admin'


def get_parent_network_for_user(user):
    """
    Get the parent GAM network for a parent user
    
    Args:
        user: User object
    
    Returns:
        GAMNetwork object or None
    """
    if not user or not user.is_authenticated:
        return None
    
    if user.role != 'parent':
        return None
    
    # Get parent network from PublisherPermission
    from .models import PublisherPermission
    
    perm = PublisherPermission.objects.filter(
        user=user,
        parent_gam_network__isnull=False
    ).select_related('parent_gam_network').first()
    
    return perm.parent_gam_network if perm else None

