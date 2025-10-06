"""
RBAC Service Layer
Production-grade permission calculation and enforcement
Based on RBAC.md specification
"""

from django.core.cache import cache
from django.db import transaction
from django.utils import timezone
from typing import Set, List, Optional, Dict, Any
import logging

from .models import (
    Permission, RolePermission, UserPermissionOverride,
    PartnerPublisherAccess, ParentNetwork, PermissionAuditLog
)
from .models import User

logger = logging.getLogger(__name__)


class RBACService:
    """
    Central service for RBAC operations
    """
    
    # Cache settings
    CACHE_TTL = 300  # 5 minutes
    PERMISSIONS_CACHE_PREFIX = 'rbac_permissions'
    USER_SCOPE_CACHE_PREFIX = 'rbac_user_scope'
    
    @classmethod
    def get_effective_permissions(cls, user: User) -> Set[str]:
        """
        Calculate effective permissions for a user
        
        Args:
            user: User object
            
        Returns:
            Set of permission keys the user has
        """
        if not user or not user.is_authenticated:
            return set()
        
        # Admin users have all permissions
        if user.role == 'ADMIN':
            return cls._get_all_permission_keys()
        
        # Check cache first
        cache_key = f"{cls.PERMISSIONS_CACHE_PREFIX}_{user.id}_{user.permissions_version}"
        cached_perms = cache.get(cache_key)
        
        if cached_perms is not None:
            return cached_perms
        
        # Calculate effective permissions
        permissions = set()
        
        # 1. Get role-based permissions
        role_permissions = RolePermission.objects.filter(
            role=user.role.upper()
        ).select_related('permission')
        
        for role_perm in role_permissions:
            permissions.add(role_perm.permission.key)
        
        # 2. Apply user-specific overrides
        overrides = UserPermissionOverride.objects.filter(
            user=user
        ).select_related('permission')
        
        for override in overrides:
            if override.allowed:
                permissions.add(override.permission.key)
            else:
                permissions.discard(override.permission.key)
        
        # 3. Apply partner permissions (for partner users)
        if user.role.upper() == 'PARTNER':
            from .models import PartnerPermission
            partner_permissions = PartnerPermission.objects.filter(
                user=user
            )
            
            for partner_perm in partner_permissions:
                permissions.add(partner_perm.permission)
        
        # Cache the result
        cache.set(cache_key, permissions, cls.CACHE_TTL)
        
        return permissions
    
    @classmethod
    def has_permission(cls, user: User, permission_key: str) -> bool:
        """
        Check if user has a specific permission
        
        Args:
            user: User object
            permission_key: Permission key to check
            
        Returns:
            True if user has permission
        """
        effective_permissions = cls.get_effective_permissions(user)
        return permission_key in effective_permissions
    
    @classmethod
    def get_user_scope(cls, user: User) -> Dict[str, Any]:
        """
        Get user's data scope (which publishers/networks they can access)
        
        Args:
            user: User object
            
        Returns:
            Dict with scope information
        """
        if not user or not user.is_authenticated:
            return {'publisher_ids': [], 'parent_network_id': None}
        
        # Check cache first
        cache_key = f"{cls.USER_SCOPE_CACHE_PREFIX}_{user.id}"
        cached_scope = cache.get(cache_key)
        
        if cached_scope is not None:
            return cached_scope
        
        scope = {
            'publisher_ids': [],
            'parent_network_id': None,
            'network_codes': []
        }
        
        if user.role.upper() == 'ADMIN':
            # Admin sees everything
            scope['publisher_ids'] = None  # None means "all"
            scope['network_codes'] = None
        elif user.role.upper() == 'PARENT':
            # Parent sees only their network
            parent_assignment = ParentNetwork.objects.filter(
                user=user
            ).select_related('parent_network').first()
            
            if parent_assignment:
                scope['parent_network_id'] = parent_assignment.parent_network.id
                # Get all publishers in this parent network
                from gam_accounts.models import MCMInvitation
                publisher_ids = MCMInvitation.objects.filter(
                    parent_network=parent_assignment.parent_network
                ).values_list('id', flat=True)
                scope['publisher_ids'] = list(publisher_ids)
                
                network_codes = MCMInvitation.objects.filter(
                    parent_network=parent_assignment.parent_network
                ).values_list('child_network_code', flat=True)
                scope['network_codes'] = list(network_codes)
        elif user.role.upper() == 'PARTNER':
            # Partner sees only assigned publishers (using old system)
            from gam_accounts.models import AssignedPartnerChildAccount
            old_assignments = AssignedPartnerChildAccount.objects.filter(
                partner=user
            ).select_related('invitation')
            
            publisher_ids = [assignment.invitation.id for assignment in old_assignments]
            network_codes = [assignment.invitation.child_network_code for assignment in old_assignments]
            
            scope['publisher_ids'] = publisher_ids
            scope['network_codes'] = network_codes
        
        # Cache the result
        cache.set(cache_key, scope, cls.CACHE_TTL)
        
        return scope
    
    @classmethod
    def scope_queryset(cls, user: User, queryset, model_name: str = None):
        """
        Apply scope filtering to a queryset based on user's role
        
        Args:
            user: User object
            queryset: Django QuerySet to filter
            model_name: Name of the model (for debugging)
            
        Returns:
            Filtered QuerySet
        """
        if not user or not user.is_authenticated:
            return queryset.none()
        
        scope = cls.get_user_scope(user)
        
        # Admin sees everything
        if scope['publisher_ids'] is None:
            return queryset
        
        # Apply scope filtering based on model
        model = queryset.model
        
        # For models with 'invitation' foreign key
        if hasattr(model, 'invitation'):
            return queryset.filter(invitation_id__in=scope['publisher_ids'])
        
        # For models with 'child_network_code'
        elif hasattr(model, 'child_network_code'):
            return queryset.filter(child_network_code__in=scope['network_codes'])
        
        # For MCMInvitation model itself
        elif model.__name__ == 'MCMInvitation':
            return queryset.filter(id__in=scope['publisher_ids'])
        
        # For models with 'parent_network'
        elif hasattr(model, 'parent_network') and scope['parent_network_id']:
            return queryset.filter(parent_network_id=scope['parent_network_id'])
        
        # For reports data with invitation relationship
        elif hasattr(model, 'invitation') and hasattr(model.invitation, 'parent_network'):
            if scope['parent_network_id']:
                return queryset.filter(invitation__parent_network_id=scope['parent_network_id'])
            else:
                return queryset.filter(invitation_id__in=scope['publisher_ids'])
        
        # Default: no filtering (should not happen)
        logger.warning(f"No scope filtering applied for model {model.__name__} and user {user.email}")
        return queryset
    
    @classmethod
    def grant_permission_override(cls, user: User, permission_key: str, granted_by: User, 
                                reason: str = "", ip_address: str = None) -> bool:
        """
        Grant a permission override to a user
        
        Args:
            user: Target user
            permission_key: Permission to grant
            granted_by: User granting the permission
            reason: Reason for granting
            ip_address: IP address of the granter
            
        Returns:
            True if successful
        """
        try:
            with transaction.atomic():
                permission = Permission.objects.get(key=permission_key)
                
                # Create or update override
                override, created = UserPermissionOverride.objects.update_or_create(
                    user=user,
                    permission=permission,
                    defaults={
                        'allowed': True,
                        'granted_by': granted_by,
                        'reason': reason
                    }
                )
                
                # Log the action
                PermissionAuditLog.objects.create(
                    action='GRANT',
                    target_user=user,
                    permission=permission,
                    performed_by=granted_by,
                    reason=reason,
                    ip_address=ip_address
                )
                
                # Clear user's permission cache
                cls._clear_user_cache(user)
                
                logger.info(f"Granted permission {permission_key} to {user.email} by {granted_by.email}")
                return True
                
        except Permission.DoesNotExist:
            logger.error(f"Permission {permission_key} does not exist")
            return False
        except Exception as e:
            logger.error(f"Failed to grant permission {permission_key} to {user.email}: {str(e)}")
            return False
    
    @classmethod
    def revoke_permission_override(cls, user: User, permission_key: str, revoked_by: User,
                                 reason: str = "", ip_address: str = None) -> bool:
        """
        Revoke a permission override from a user
        
        Args:
            user: Target user
            permission_key: Permission to revoke
            revoked_by: User revoking the permission
            reason: Reason for revoking
            ip_address: IP address of the revoker
            
        Returns:
            True if successful
        """
        try:
            with transaction.atomic():
                permission = Permission.objects.get(key=permission_key)
                
                # Create or update override (set to False)
                override, created = UserPermissionOverride.objects.update_or_create(
                    user=user,
                    permission=permission,
                    defaults={
                        'allowed': False,
                        'granted_by': revoked_by,
                        'reason': reason
                    }
                )
                
                # Log the action
                PermissionAuditLog.objects.create(
                    action='REVOKE',
                    target_user=user,
                    permission=permission,
                    performed_by=revoked_by,
                    reason=reason,
                    ip_address=ip_address
                )
                
                # Clear user's permission cache
                cls._clear_user_cache(user)
                
                logger.info(f"Revoked permission {permission_key} from {user.email} by {revoked_by.email}")
                return True
                
        except Permission.DoesNotExist:
            logger.error(f"Permission {permission_key} does not exist")
            return False
        except Exception as e:
            logger.error(f"Failed to revoke permission {permission_key} from {user.email}: {str(e)}")
            return False
    
    @classmethod
    def assign_publisher_to_partner(cls, partner: User, publisher, granted_by: User,
                                  reason: str = "", ip_address: str = None) -> bool:
        """
        Assign a publisher to a partner
        
        Args:
            partner: Partner user
            publisher: Publisher (MCMInvitation) object
            granted_by: User granting the assignment
            reason: Reason for assignment
            ip_address: IP address of the granter
            
        Returns:
            True if successful
        """
        try:
            with transaction.atomic():
                # Create assignment
                assignment, created = PartnerPublisherAccess.objects.update_or_create(
                    partner=partner,
                    publisher=publisher,
                    defaults={
                        'granted_by': granted_by,
                        'notes': reason
                    }
                )
                
                # Log the action
                PermissionAuditLog.objects.create(
                    action='ASSIGN_PUBLISHER',
                    target_user=partner,
                    publisher=publisher,
                    performed_by=granted_by,
                    reason=reason,
                    ip_address=ip_address
                )
                
                # Clear user's scope cache
                cls._clear_user_cache(partner)
                
                logger.info(f"Assigned publisher {publisher.child_network_name} to partner {partner.email} by {granted_by.email}")
                return True
                
        except Exception as e:
            logger.error(f"Failed to assign publisher to partner {partner.email}: {str(e)}")
            return False
    
    @classmethod
    def unassign_publisher_from_partner(cls, partner: User, publisher, revoked_by: User,
                                      reason: str = "", ip_address: str = None) -> bool:
        """
        Unassign a publisher from a partner
        
        Args:
            partner: Partner user
            publisher: Publisher (MCMInvitation) object
            revoked_by: User revoking the assignment
            reason: Reason for unassignment
            ip_address: IP address of the revoker
            
        Returns:
            True if successful
        """
        try:
            with transaction.atomic():
                # Remove assignment
                deleted_count, _ = PartnerPublisherAccess.objects.filter(
                    partner=partner,
                    publisher=publisher
                ).delete()
                
                if deleted_count > 0:
                    # Log the action
                    PermissionAuditLog.objects.create(
                        action='UNASSIGN_PUBLISHER',
                        target_user=partner,
                        publisher=publisher,
                        performed_by=revoked_by,
                        reason=reason,
                        ip_address=ip_address
                    )
                    
                    # Clear user's scope cache
                    cls._clear_user_cache(partner)
                    
                    logger.info(f"Unassigned publisher {publisher.child_network_name} from partner {partner.email} by {revoked_by.email}")
                    return True
                else:
                    logger.warning(f"No assignment found to remove for partner {partner.email} and publisher {publisher.child_network_name}")
                    return False
                
        except Exception as e:
            logger.error(f"Failed to unassign publisher from partner {partner.email}: {str(e)}")
            return False
    
    @classmethod
    def assign_parent_network(cls, parent_user: User, parent_network, granted_by: User,
                            reason: str = "", ip_address: str = None) -> bool:
        """
        Assign a parent network to a parent user
        
        Args:
            parent_user: Parent user
            parent_network: Parent network object
            granted_by: User granting the assignment
            reason: Reason for assignment
            ip_address: IP address of the granter
            
        Returns:
            True if successful
        """
        try:
            with transaction.atomic():
                # Create or update assignment
                assignment, created = ParentNetwork.objects.update_or_create(
                    user=parent_user,
                    defaults={
                        'parent_network': parent_network,
                        'granted_by': granted_by
                    }
                )
                
                # Log the action
                PermissionAuditLog.objects.create(
                    action='ASSIGN_PARENT',
                    target_user=parent_user,
                    parent_network=parent_network,
                    performed_by=granted_by,
                    reason=reason,
                    ip_address=ip_address
                )
                
                # Clear user's scope cache
                cls._clear_user_cache(parent_user)
                
                logger.info(f"Assigned parent network {parent_network.network_name} to parent user {parent_user.email} by {granted_by.email}")
                return True
                
        except Exception as e:
            logger.error(f"Failed to assign parent network to parent user {parent_user.email}: {str(e)}")
            return False
    
    @classmethod
    def _get_all_permission_keys(cls) -> Set[str]:
        """Get all permission keys from the database"""
        return set(Permission.objects.values_list('key', flat=True))
    
    @classmethod
    def _clear_user_cache(cls, user: User):
        """Clear all cached data for a user"""
        # Clear permission cache
        cache.delete(f"{cls.PERMISSIONS_CACHE_PREFIX}_{user.id}_{user.permissions_version}")
        
        # Clear scope cache
        cache.delete(f"{cls.USER_SCOPE_CACHE_PREFIX}_{user.id}")
        
        # Increment permissions version to invalidate all cached permissions
        user.permissions_version += 1
        user.save(update_fields=['permissions_version'])


# Convenience functions for backward compatibility
def has_permission(user: User, permission_key: str) -> bool:
    """Check if user has a specific permission"""
    return RBACService.has_permission(user, permission_key)


def get_effective_permissions(user: User) -> Set[str]:
    """Get effective permissions for a user"""
    return RBACService.get_effective_permissions(user)


def scope_queryset(user: User, queryset, model_name: str = None):
    """Apply scope filtering to a queryset"""
    return RBACService.scope_queryset(user, queryset, model_name)
