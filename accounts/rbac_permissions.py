"""
RBAC Permission Classes and Decorators
Production-grade permission enforcement for DRF views
"""

from functools import wraps
from typing import List, Optional
from rest_framework import permissions
from rest_framework.response import Response
from rest_framework import status
import logging

from .rbac_service import RBACService

logger = logging.getLogger(__name__)


class RBACPermission(permissions.BasePermission):
    """
    Base RBAC permission class for DRF views
    """
    
    def has_permission(self, request, view):
        """
        Check if user has permission for this view
        
        Override in subclasses to implement specific permission logic
        """
        if not request.user or not request.user.is_authenticated:
            return False
        
        return True


class HasPermission(RBACPermission):
    """
    Permission class that requires a specific permission
    
    Usage:
        class MyView(APIView):
            permission_classes = [IsAuthenticated, HasPermission]
            required_permission = 'reports.view'
    """
    
    def has_permission(self, request, view):
        if not super().has_permission(request, view):
            return False
        
        # Get required permission from view
        required_permission = getattr(view, 'required_permission', None)
        
        if not required_permission:
            # If no permission specified, allow access
            return True
        
        return RBACService.has_permission(request.user, required_permission)


class HasAnyPermission(RBACPermission):
    """
    Permission class that requires any of the specified permissions
    
    Usage:
        class MyView(APIView):
            permission_classes = [IsAuthenticated, HasAnyPermission]
            required_permissions = ['reports.view', 'reports.export']
    """
    
    def has_permission(self, request, view):
        if not super().has_permission(request, view):
            return False
        
        # Get required permissions from view
        required_permissions = getattr(view, 'required_permissions', [])
        
        if not required_permissions:
            # If no permissions specified, allow access
            return True
        
        # Check if user has any of the required permissions
        for permission in required_permissions:
            if RBACService.has_permission(request.user, permission):
                return True
        
        return False


class HasAllPermissions(RBACPermission):
    """
    Permission class that requires all of the specified permissions
    
    Usage:
        class MyView(APIView):
            permission_classes = [IsAuthenticated, HasAllPermissions]
            required_permissions = ['reports.view', 'reports.export']
    """
    
    def has_permission(self, request, view):
        if not super().has_permission(request, view):
            return False
        
        # Get required permissions from view
        required_permissions = getattr(view, 'required_permissions', [])
        
        if not required_permissions:
            # If no permissions specified, allow access
            return True
        
        # Check if user has all of the required permissions
        for permission in required_permissions:
            if not RBACService.has_permission(request.user, permission):
                return False
        
        return True


class AdminOnlyPermission(RBACPermission):
    """
    Permission class that requires ADMIN role
    
    Usage:
        class MyView(APIView):
            permission_classes = [IsAuthenticated, AdminOnlyPermission]
    """
    
    def has_permission(self, request, view):
        if not super().has_permission(request, view):
            return False
        
        return request.user.role == 'ADMIN'


class ParentOrAdminPermission(RBACPermission):
    """
    Permission class that requires PARENT or ADMIN role
    
    Usage:
        class MyView(APIView):
            permission_classes = [IsAuthenticated, ParentOrAdminPermission]
    """
    
    def has_permission(self, request, view):
        if not super().has_permission(request, view):
            return False
        
        return request.user.role in ['ADMIN', 'PARENT']


class ScopedQuerysetMixin:
    """
    Mixin that automatically applies scope filtering to querysets
    """
    
    def get_queryset(self):
        """
        Override to apply scope filtering
        """
        # Try to get queryset from parent class
        try:
            queryset = super().get_queryset()
        except (AttributeError, AssertionError):
            # If parent doesn't have queryset, build it from scratch
            from gam_accounts.models import MCMInvitation
            queryset = MCMInvitation.objects.all()
        
        # Apply scope filtering
        return RBACService.scope_queryset(self.request.user, queryset)


class ScopedFilterMixin:
    """
    Mixin that applies scope filtering to filter backends
    """
    
    def filter_queryset(self, queryset):
        """
        Apply scope filtering to the queryset
        """
        # Apply RBAC scope filtering first
        queryset = RBACService.scope_queryset(self.request.user, queryset)
        
        # Then apply other filters
        return super().filter_queryset(queryset)


def require_permission(permission_key: str):
    """
    Decorator to require a specific permission for a view function
    
    Usage:
        @require_permission('reports.view')
        def my_view(request):
            ...
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapped_view(request, *args, **kwargs):
            if not request.user or not request.user.is_authenticated:
                return Response(
                    {'error': 'Authentication required'},
                    status=status.HTTP_401_UNAUTHORIZED
                )
            
            if not RBACService.has_permission(request.user, permission_key):
                return Response(
                    {
                        'error': 'Permission denied',
                        'detail': f'You do not have permission: {permission_key}',
                        'required_permission': permission_key
                    },
                    status=status.HTTP_403_FORBIDDEN
                )
            
            return view_func(request, *args, **kwargs)
        return wrapped_view
    return decorator


def require_any_permission(permission_keys: List[str]):
    """
    Decorator to require any of the specified permissions
    
    Usage:
        @require_any_permission(['reports.view', 'reports.export'])
        def my_view(request):
            ...
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapped_view(request, *args, **kwargs):
            if not request.user or not request.user.is_authenticated:
                return Response(
                    {'error': 'Authentication required'},
                    status=status.HTTP_401_UNAUTHORIZED
                )
            
            # Check if user has any of the required permissions
            has_permission = False
            for permission_key in permission_keys:
                if RBACService.has_permission(request.user, permission_key):
                    has_permission = True
                    break
            
            if not has_permission:
                return Response(
                    {
                        'error': 'Permission denied',
                        'detail': f'You do not have any of the required permissions: {permission_keys}',
                        'required_permissions': permission_keys
                    },
                    status=status.HTTP_403_FORBIDDEN
                )
            
            return view_func(request, *args, **kwargs)
        return wrapped_view
    return decorator


def require_all_permissions(permission_keys: List[str]):
    """
    Decorator to require all of the specified permissions
    
    Usage:
        @require_all_permissions(['reports.view', 'reports.export'])
        def my_view(request):
            ...
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapped_view(request, *args, **kwargs):
            if not request.user or not request.user.is_authenticated:
                return Response(
                    {'error': 'Authentication required'},
                    status=status.HTTP_401_UNAUTHORIZED
                )
            
            # Check if user has all of the required permissions
            for permission_key in permission_keys:
                if not RBACService.has_permission(request.user, permission_key):
                    return Response(
                        {
                            'error': 'Permission denied',
                            'detail': f'You do not have permission: {permission_key}',
                            'required_permissions': permission_keys,
                            'missing_permission': permission_key
                        },
                        status=status.HTTP_403_FORBIDDEN
                    )
            
            return view_func(request, *args, **kwargs)
        return wrapped_view
    return decorator


def require_admin_role(view_func):
    """
    Decorator to require ADMIN role
    
    Usage:
        @require_admin_role
        def my_view(request):
            ...
    """
    @wraps(view_func)
    def wrapped_view(request, *args, **kwargs):
        if not request.user or not request.user.is_authenticated:
            return Response(
                {'error': 'Authentication required'},
                status=status.HTTP_401_UNAUTHORIZED
            )
        
        if request.user.role != 'ADMIN':
            return Response(
                {
                    'error': 'Admin access required',
                    'detail': 'This action requires admin privileges'
                },
                status=status.HTTP_403_FORBIDDEN
            )
        
        return view_func(request, *args, **kwargs)
    return wrapped_view


def require_parent_or_admin_role(view_func):
    """
    Decorator to require PARENT or ADMIN role
    
    Usage:
        @require_parent_or_admin_role
        def my_view(request):
            ...
    """
    @wraps(view_func)
    def wrapped_view(request, *args, **kwargs):
        if not request.user or not request.user.is_authenticated:
            return Response(
                {'error': 'Authentication required'},
                status=status.HTTP_401_UNAUTHORIZED
            )
        
        if request.user.role not in ['ADMIN', 'PARENT']:
            return Response(
                {
                    'error': 'Parent or admin access required',
                    'detail': 'This action requires parent network or admin privileges'
                },
                status=status.HTTP_403_FORBIDDEN
            )
        
        return view_func(request, *args, **kwargs)
    return wrapped_view
