"""
RBAC API Views
Admin endpoints for managing permissions and user access
"""

from rest_framework import status, generics, permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.views import APIView
from django.shortcuts import get_object_or_404
from django.db import transaction
from django.contrib.auth import get_user_model

from .models import (
    Permission, RolePermission, UserPermissionOverride,
    PartnerPublisherAccess, ParentNetwork, PermissionAuditLog
)
from .rbac_service import RBACService
from .rbac_permissions import AdminOnlyPermission, HasPermission
from .rbac_serializers import (
    PermissionSerializer, RolePermissionSerializer,
    UserPermissionOverrideSerializer, PartnerPublisherAccessSerializer,
    ParentNetworkSerializer, PermissionAuditLogSerializer
)

User = get_user_model()


class PermissionListView(generics.ListAPIView):
    """
    GET /api/rbac/permissions/
    List all permissions (Admin only)
    """
    queryset = Permission.objects.all()
    serializer_class = PermissionSerializer
    permission_classes = [permissions.IsAuthenticated, AdminOnlyPermission]
    filterset_fields = ['category']


class RolePermissionListView(generics.ListAPIView):
    """
    GET /api/rbac/role-permissions/
    List all role permission defaults (Admin only)
    """
    queryset = RolePermission.objects.select_related('permission')
    serializer_class = RolePermissionSerializer
    permission_classes = [permissions.IsAuthenticated, AdminOnlyPermission]
    filterset_fields = ['role']


class UserPermissionOverridesView(APIView):
    """
    GET /api/rbac/users/{user_id}/permissions/
    PATCH /api/rbac/users/{user_id}/permissions/
    Manage user permission overrides (Admin only)
    """
    permission_classes = [permissions.IsAuthenticated, AdminOnlyPermission]
    
    def get(self, request, user_id):
        """Get user's permission overrides"""
        user = get_object_or_404(User, id=user_id)
        
        # Get effective permissions
        effective_permissions = RBACService.get_effective_permissions(user)
        
        # Get role permissions
        role_permissions = RolePermission.objects.filter(
            role=user.role
        ).select_related('permission')
        
        # Get user overrides
        user_overrides = UserPermissionOverride.objects.filter(
            user=user
        ).select_related('permission', 'granted_by')
        
        # Build response
        role_perms = {}
        for rp in role_permissions:
            role_perms[rp.permission.key] = {
                'key': rp.permission.key,
                'description': rp.permission.description,
                'category': rp.permission.category,
                'source': 'role',
                'granted': True
            }
        
        user_overrides_dict = {}
        for override in user_overrides:
            user_overrides_dict[override.permission.key] = {
                'key': override.permission.key,
                'description': override.permission.description,
                'category': override.permission.category,
                'source': 'override',
                'granted': override.allowed,
                'granted_by': override.granted_by.email if override.granted_by else None,
                'reason': override.reason,
                'created_at': override.created_at
            }
        
        # Get all permissions
        all_permissions = Permission.objects.all()
        permissions_data = []
        
        for perm in all_permissions:
            if perm.key in user_overrides_dict:
                # User has override
                permissions_data.append(user_overrides_dict[perm.key])
            elif perm.key in role_perms:
                # User has role permission
                permissions_data.append(role_perms[perm.key])
            else:
                # User doesn't have this permission
                permissions_data.append({
                    'key': perm.key,
                    'description': perm.description,
                    'category': perm.category,
                    'source': 'none',
                    'granted': False
                })
        
        return Response({
            'user': {
                'id': user.id,
                'email': user.email,
                'role': user.role,
                'permissions_version': user.permissions_version
            },
            'effective_permissions': list(effective_permissions),
            'permissions': permissions_data
        })
    
    def patch(self, request, user_id):
        """Update user's permission overrides"""
        user = get_object_or_404(User, id=user_id)
        overrides_data = request.data.get('overrides', [])
        
        try:
            with transaction.atomic():
                results = []
                
                for override_data in overrides_data:
                    permission_key = override_data.get('permission_key')
                    allowed = override_data.get('allowed', False)
                    reason = override_data.get('reason', '')
                    
                    if not permission_key:
                        continue
                    
                    # Grant or revoke permission
                    if allowed:
                        success = RBACService.grant_permission_override(
                            user=user,
                            permission_key=permission_key,
                            granted_by=request.user,
                            reason=reason,
                            ip_address=self.get_client_ip(request)
                        )
                    else:
                        success = RBACService.revoke_permission_override(
                            user=user,
                            permission_key=permission_key,
                            revoked_by=request.user,
                            reason=reason,
                            ip_address=self.get_client_ip(request)
                        )
                    
                    results.append({
                        'permission_key': permission_key,
                        'allowed': allowed,
                        'success': success
                    })
                
                return Response({
                    'message': 'Permission overrides updated successfully',
                    'results': results
                })
                
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    def get_client_ip(self, request):
        """Get client IP address"""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip


class PartnerPublisherAccessView(APIView):
    """
    GET /api/rbac/partners/{partner_id}/publishers/
    POST /api/rbac/partners/{partner_id}/publishers/
    Manage partner to publisher assignments (Admin only)
    """
    permission_classes = [permissions.IsAuthenticated, AdminOnlyPermission]
    
    def get(self, request, partner_id):
        """Get partner's assigned publishers"""
        partner = get_object_or_404(User, id=partner_id, role='PARTNER')
        
        assignments = PartnerPublisherAccess.objects.filter(
            partner=partner
        ).select_related('publisher', 'granted_by')
        
        serializer = PartnerPublisherAccessSerializer(assignments, many=True)
        
        return Response({
            'partner': {
                'id': partner.id,
                'email': partner.email,
                'role': partner.role
            },
            'assignments': serializer.data
        })
    
    def post(self, request, partner_id):
        """Assign publishers to partner"""
        partner = get_object_or_404(User, id=partner_id, role='PARTNER')
        publisher_ids = request.data.get('publisher_ids', [])
        reason = request.data.get('reason', '')
        
        try:
            from gam_accounts.models import MCMInvitation
            
            results = []
            for publisher_id in publisher_ids:
                publisher = get_object_or_404(MCMInvitation, id=publisher_id)
                
                success = RBACService.assign_publisher_to_partner(
                    partner=partner,
                    publisher=publisher,
                    granted_by=request.user,
                    reason=reason,
                    ip_address=self.get_client_ip(request)
                )
                
                results.append({
                    'publisher_id': publisher_id,
                    'publisher_name': publisher.child_network_name,
                    'success': success
                })
            
            return Response({
                'message': 'Publisher assignments updated successfully',
                'results': results
            })
            
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    def delete(self, request, partner_id):
        """Unassign publishers from partner"""
        partner = get_object_or_404(User, id=partner_id, role='PARTNER')
        publisher_ids = request.data.get('publisher_ids', [])
        reason = request.data.get('reason', '')
        
        try:
            from gam_accounts.models import MCMInvitation
            
            results = []
            for publisher_id in publisher_ids:
                publisher = get_object_or_404(MCMInvitation, id=publisher_id)
                
                success = RBACService.unassign_publisher_from_partner(
                    partner=partner,
                    publisher=publisher,
                    revoked_by=request.user,
                    reason=reason,
                    ip_address=self.get_client_ip(request)
                )
                
                results.append({
                    'publisher_id': publisher_id,
                    'publisher_name': publisher.child_network_name,
                    'success': success
                })
            
            return Response({
                'message': 'Publisher assignments removed successfully',
                'results': results
            })
            
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    def get_client_ip(self, request):
        """Get client IP address"""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip


class ParentNetworkAssignmentView(APIView):
    """
    GET /api/rbac/parents/{parent_id}/network/
    PATCH /api/rbac/parents/{parent_id}/network/
    Manage parent network assignments (Admin only)
    """
    permission_classes = [permissions.IsAuthenticated, AdminOnlyPermission]
    
    def get(self, request, parent_id):
        """Get parent's network assignment"""
        parent = get_object_or_404(User, id=parent_id, role='PARENT')
        
        try:
            assignment = ParentNetwork.objects.get(user=parent)
            serializer = ParentNetworkSerializer(assignment)
            
            return Response({
                'parent': {
                    'id': parent.id,
                    'email': parent.email,
                    'role': parent.role
                },
                'assignment': serializer.data
            })
        except ParentNetwork.DoesNotExist:
            return Response({
                'parent': {
                    'id': parent.id,
                    'email': parent.email,
                    'role': parent.role
                },
                'assignment': None
            })
    
    def patch(self, request, parent_id):
        """Assign parent network to parent user"""
        parent = get_object_or_404(User, id=parent_id, role='PARENT')
        parent_network_id = request.data.get('parent_network_id')
        reason = request.data.get('reason', '')
        
        if not parent_network_id:
            return Response(
                {'error': 'parent_network_id is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            from gam_accounts.models import GAMNetwork
            parent_network = get_object_or_404(GAMNetwork, id=parent_network_id)
            
            success = RBACService.assign_parent_network(
                parent_user=parent,
                parent_network=parent_network,
                granted_by=request.user,
                reason=reason,
                ip_address=self.get_client_ip(request)
            )
            
            if success:
                return Response({
                    'message': 'Parent network assignment updated successfully',
                    'parent_network': {
                        'id': parent_network.id,
                        'name': parent_network.network_name,
                        'code': parent_network.network_code
                    }
                })
            else:
                return Response(
                    {'error': 'Failed to assign parent network'},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
                
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    def get_client_ip(self, request):
        """Get client IP address"""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip


class PermissionAuditLogView(generics.ListAPIView):
    """
    GET /api/rbac/audit-logs/
    List permission audit logs (Admin only)
    """
    queryset = PermissionAuditLog.objects.select_related(
        'target_user', 'permission', 'publisher', 'parent_network', 'performed_by'
    )
    serializer_class = PermissionAuditLogSerializer
    permission_classes = [permissions.IsAuthenticated, AdminOnlyPermission]
    filterset_fields = ['action', 'target_user', 'performed_by']


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def user_claims_view(request):
    """
    GET /api/rbac/me/claims
    Get current user's claims and permissions
    """
    user = request.user
    
    # Get effective permissions
    effective_permissions = RBACService.get_effective_permissions(user)
    
    # Get user scope
    scope = RBACService.get_user_scope(user)
    
    # Build claims
    claims = {
        'userId': str(user.id),
        'email': user.email,
        'role': user.role,
        'effectivePermissions': list(effective_permissions),
        'permissionsVersion': user.permissions_version,
        'scope': scope
    }
    
    # Add role-specific information
    if user.role == 'PARENT':
        parent_assignment = ParentNetwork.objects.filter(user=user).first()
        if parent_assignment:
            claims['parentNetwork'] = {
                'id': parent_assignment.parent_network.id,
                'name': parent_assignment.parent_network.network_name,
                'code': parent_assignment.parent_network.network_code
            }
    
    return Response(claims)
