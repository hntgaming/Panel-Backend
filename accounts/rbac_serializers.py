"""
RBAC Serializers
Serializers for RBAC models and API responses
"""

from rest_framework import serializers
from .models import (
    Permission, RolePermission, UserPermissionOverride,
    PartnerPublisherAccess, ParentNetwork, PermissionAuditLog
)


class PermissionSerializer(serializers.ModelSerializer):
    """Serializer for Permission model"""
    
    class Meta:
        model = Permission
        fields = ['id', 'key', 'description', 'category', 'created_at', 'updated_at']


class RolePermissionSerializer(serializers.ModelSerializer):
    """Serializer for RolePermission model"""
    permission = PermissionSerializer(read_only=True)
    permission_key = serializers.CharField(source='permission.key', read_only=True)
    
    class Meta:
        model = RolePermission
        fields = ['id', 'role', 'permission', 'permission_key', 'created_at', 'updated_at']


class UserPermissionOverrideSerializer(serializers.ModelSerializer):
    """Serializer for UserPermissionOverride model"""
    permission = PermissionSerializer(read_only=True)
    permission_key = serializers.CharField(source='permission.key', read_only=True)
    granted_by_email = serializers.CharField(source='granted_by.email', read_only=True)
    
    class Meta:
        model = UserPermissionOverride
        fields = [
            'id', 'user', 'permission', 'permission_key', 'allowed',
            'granted_by', 'granted_by_email', 'reason', 'created_at', 'updated_at'
        ]
        read_only_fields = ['user', 'granted_by']


class PartnerPublisherAccessSerializer(serializers.ModelSerializer):
    """Serializer for PartnerPublisherAccess model"""
    partner_email = serializers.CharField(source='partner.email', read_only=True)
    publisher_name = serializers.CharField(source='publisher.child_network_name', read_only=True)
    publisher_code = serializers.CharField(source='publisher.child_network_code', read_only=True)
    granted_by_email = serializers.CharField(source='granted_by.email', read_only=True)
    
    class Meta:
        model = PartnerPublisherAccess
        fields = [
            'id', 'partner', 'partner_email', 'publisher', 'publisher_name',
            'publisher_code', 'granted_by', 'granted_by_email', 'notes',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['partner', 'granted_by']


class ParentNetworkSerializer(serializers.ModelSerializer):
    """Serializer for ParentNetwork model"""
    user_email = serializers.CharField(source='user.email', read_only=True)
    network_name = serializers.CharField(source='parent_network.network_name', read_only=True)
    network_code = serializers.CharField(source='parent_network.network_code', read_only=True)
    granted_by_email = serializers.CharField(source='granted_by.email', read_only=True)
    
    class Meta:
        model = ParentNetwork
        fields = [
            'id', 'user', 'user_email', 'parent_network', 'network_name',
            'network_code', 'granted_by', 'granted_by_email', 'created_at', 'updated_at'
        ]
        read_only_fields = ['user', 'granted_by']


class PermissionAuditLogSerializer(serializers.ModelSerializer):
    """Serializer for PermissionAuditLog model"""
    target_user_email = serializers.CharField(source='target_user.email', read_only=True)
    permission_key = serializers.CharField(source='permission.key', read_only=True)
    publisher_name = serializers.CharField(source='publisher.child_network_name', read_only=True)
    parent_network_name = serializers.CharField(source='parent_network.network_name', read_only=True)
    performed_by_email = serializers.CharField(source='performed_by.email', read_only=True)
    
    class Meta:
        model = PermissionAuditLog
        fields = [
            'id', 'action', 'target_user', 'target_user_email', 'permission',
            'permission_key', 'publisher', 'publisher_name', 'parent_network',
            'parent_network_name', 'performed_by', 'performed_by_email',
            'reason', 'ip_address', 'created_at'
        ]
        read_only_fields = ['performed_by']


class UserPermissionOverrideUpdateSerializer(serializers.Serializer):
    """Serializer for updating user permission overrides"""
    permission_key = serializers.CharField(max_length=100)
    allowed = serializers.BooleanField()
    reason = serializers.CharField(max_length=500, required=False, allow_blank=True)


class PartnerPublisherAssignmentSerializer(serializers.Serializer):
    """Serializer for partner publisher assignments"""
    publisher_ids = serializers.ListField(
        child=serializers.IntegerField(),
        allow_empty=False
    )
    reason = serializers.CharField(max_length=500, required=False, allow_blank=True)


class ParentNetworkAssignmentSerializer(serializers.Serializer):
    """Serializer for parent network assignments"""
    parent_network_id = serializers.IntegerField()
    reason = serializers.CharField(max_length=500, required=False, allow_blank=True)


class UserClaimsSerializer(serializers.Serializer):
    """Serializer for user claims response"""
    userId = serializers.CharField()
    email = serializers.EmailField()
    role = serializers.CharField()
    effectivePermissions = serializers.ListField(child=serializers.CharField())
    permissionsVersion = serializers.IntegerField()
    scope = serializers.DictField()
    parentNetwork = serializers.DictField(required=False)


class PermissionSummarySerializer(serializers.Serializer):
    """Serializer for permission summary"""
    key = serializers.CharField()
    description = serializers.CharField()
    category = serializers.CharField()
    source = serializers.CharField()  # 'role', 'override', or 'none'
    granted = serializers.BooleanField()
    granted_by = serializers.CharField(required=False, allow_null=True)
    reason = serializers.CharField(required=False, allow_blank=True)
    created_at = serializers.DateTimeField(required=False, allow_null=True)
