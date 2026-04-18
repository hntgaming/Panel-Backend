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
    if user.is_staff or user.is_superuser or user.role.upper() == 'ADMIN':
        return {perm: True for perm in PermissionType.ALL_PERMISSIONS}
    
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
    if user.is_staff or user.is_superuser or user.role.upper() == 'ADMIN':
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


class IsPartnerAdminOrAdmin(permissions.BasePermission):
    """Allow access to partner_admin and admin roles only."""

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        return request.user.role in ('admin', 'partner_admin')


class IsSubPublisherOwnerOrAdmin(permissions.BasePermission):
    """
    Object-level: allow if the requesting user is the sub-publisher's
    parent_publisher, or an admin.
    """

    def has_object_permission(self, request, view, obj):
        if request.user.role == 'admin':
            return True
        if request.user.role == 'partner_admin':
            return getattr(obj, 'parent_publisher_id', None) == request.user.id
        if request.user.role == 'sub_publisher':
            return obj.id == request.user.id
        return False


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



