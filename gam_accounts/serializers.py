from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import AssignedPartnerChildAccount, GAMNetwork, MCMInvitation

User = get_user_model()

class GAMNetworkSerializer(serializers.ModelSerializer):
    is_parent = serializers.ReadOnlyField()
    is_child = serializers.ReadOnlyField()
    child_networks_count = serializers.SerializerMethodField()
    
    class Meta:
        model = GAMNetwork
        fields = [
            'id', 'network_code', 'network_name', 'display_name',
            'network_type', 'currency_code', 'time_zone', 'status',
            'parent_network', 'service_account_email', 'service_account_added',
            'service_account_enabled', 'api_version', 'is_parent', 'is_child', 'child_networks_count',
            'created_at', 'updated_at', 'last_sync'
        ]
        read_only_fields = [
            'id', 'created_at', 'updated_at', 'last_sync',
            'is_parent', 'is_child', 'child_networks_count'
        ]
    
    def get_child_networks_count(self, obj):
        return obj.child_networks.filter(status='active').count()

class GAMNetworkListSerializer(serializers.ModelSerializer):
    """Simplified serializer for listing networks"""
    is_parent = serializers.ReadOnlyField()
    child_networks_count = serializers.SerializerMethodField()
    
    class Meta:
        model = GAMNetwork
        fields = [
            'id', 'network_code', 'network_name', 'network_type',
            'status', 'currency_code', 'is_parent', 'child_networks_count',
            'last_sync'
        ]
    
    def get_child_networks_count(self, obj):
        return obj.child_networks.filter(status='active').count()

# UPDATED: Enhanced MCMInvitationSerializer with new API fields
class MCMInvitationSerializer(serializers.ModelSerializer):
    parent_network_name = serializers.CharField(source='parent_network.network_name', read_only=True)
    parent_network_code = serializers.CharField(source='parent_network.network_code', read_only=True)
    parent_network = GAMNetworkSerializer(read_only=True)
    invited_by_username = serializers.CharField(source='invited_by.username', read_only=True)
    days_until_expiry = serializers.SerializerMethodField()
    child_revenue_percentage = serializers.ReadOnlyField()
    is_expired = serializers.ReadOnlyField()
    
    class Meta:
        model = MCMInvitation
        fields = [
            'id', 'parent_network', 'parent_network_name', 'parent_network_code',
            'child_network_code', 'child_network_name', 'primary_contact_email',
            'delegation_type', 'revenue_share_percentage', 'child_revenue_percentage',
            'gam_company_id', 'api_method_used', 'real_invitation_sent',
            'invitation_id', 'status', 'invited_by', 'invited_by_username',
            'days_until_expiry', 'is_expired', 'created_at', 'updated_at',
            'expires_at', 'accepted_at','site', 'comments', 'invite_type','user_status',
            'service_account_enabled'
        ]
        read_only_fields = [
            'id', 'invitation_id', 'gam_company_id', 'api_method_used', 
            'real_invitation_sent', 'created_at', 'updated_at',
            'parent_network_name', 'parent_network_code', 'invited_by_username', 
            'days_until_expiry', 'child_revenue_percentage', 'is_expired',
            'site', 'comments', 'invite_type'
        ]
    
    def get_days_until_expiry(self, obj):
        return obj.days_until_expiry
    
    def update(self, instance, validated_data):
        # Auto-disable service key for policy violations and invalid activity
        new_status = validated_data.get('status')
        if new_status in ['closed_policy_violation', 'closed_invalid_activity']:
            validated_data['service_account_enabled'] = False
        
        return super().update(instance, validated_data)

# UPDATED: Enhanced SendMCMInvitationSerializer with API support
class SendMCMInvitationSerializer(serializers.Serializer):
    parent_network_code = serializers.CharField(max_length=20)
    child_network_code = serializers.CharField(max_length=20)
    child_network_name = serializers.CharField(max_length=255, required=False, allow_blank=True)
    primary_contact_email = serializers.EmailField(
        help_text="Email address where GAM invitation will be sent"
    )
    delegation_type = serializers.ChoiceField(
        choices=[
            ('MANAGE_INVENTORY', 'Manage Inventory'),
            ('MANAGE_ACCOUNT', 'Manage Account')
        ],
        default='MANAGE_INVENTORY',
        help_text="Type of MCM delegation to request"
    )
    revenue_share_percentage = serializers.IntegerField(
        min_value=0, 
        max_value=100, 
        required=False,
        help_text="Required for MANAGE_ACCOUNT. Percentage parent keeps (0-100)"
    )
    force_manual = serializers.BooleanField(
        default=False,
        help_text="Set to true to skip API and use manual workflow only"
    )
    site = serializers.CharField(required=False, allow_blank=True)
    comments = serializers.CharField(required=False, allow_blank=True)

    def validate_parent_network_code(self, value):
        try:
            network = GAMNetwork.objects.get(network_code=value, network_type='parent')
            if network.status != 'active':
                raise serializers.ValidationError("Parent network is not active")
            return value
        except GAMNetwork.DoesNotExist:
            raise serializers.ValidationError("Parent network not found")

    def validate_child_network_code(self, value):
        if GAMNetwork.objects.filter(network_code=value, parent_network__isnull=False).exists():
            raise serializers.ValidationError("This network is already connected to a parent")
        
        if MCMInvitation.objects.filter(
            child_network_code=value,
            status__in=['pending', 'awaiting_manual_send']
        ).exists():
            raise serializers.ValidationError("There's already a pending invitation for this network")
        
        return value

    def validate(self, data):
        if data['delegation_type'] == 'MANAGE_ACCOUNT':
            if data.get('revenue_share_percentage') is None:
                raise serializers.ValidationError({
                    'revenue_share_percentage': 'This field is required for MANAGE_ACCOUNT delegation'
                })
        elif data['delegation_type'] == 'MANAGE_INVENTORY':
            if data.get('revenue_share_percentage'):
                data.pop('revenue_share_percentage', None)
        return data

    def create(self, validated_data):
        validated_data["invite_type"] = "invitation"  # Not from frontend
        return MCMInvitation.objects.create(**validated_data)

# NEW: Detailed MCM invitation status serializer
class MCMInvitationStatusSerializer(serializers.ModelSerializer):
    """Detailed serializer for MCM invitation status with all API tracking fields"""
    parent_network_name = serializers.CharField(source='parent_network.network_name', read_only=True)
    parent_network_code = serializers.CharField(source='parent_network.network_code', read_only=True)
    invited_by_username = serializers.CharField(source='invited_by.username', read_only=True)
    invited_by_email = serializers.CharField(source='invited_by.email', read_only=True)
    days_until_expiry = serializers.ReadOnlyField()
    child_revenue_percentage = serializers.ReadOnlyField()
    is_expired = serializers.ReadOnlyField()
    
    class Meta:
        model = MCMInvitation
        fields = [
            'id', 'invitation_id', 'child_network_code', 'child_network_name',
            'primary_contact_email', 'delegation_type', 'revenue_share_percentage',
            'child_revenue_percentage', 'gam_company_id', 'api_method_used', 
            'real_invitation_sent', 'status', 'created_at', 'expires_at', 
            'accepted_at', 'updated_at', 'parent_network_name', 'parent_network_code',
            'invited_by_username', 'invited_by_email', 'days_until_expiry', 'is_expired',
            'site', 'comments', 'invite_type'
        ]

# NEW: MCM invitation list serializer (simplified for listing)
class MCMInvitationListSerializer(serializers.ModelSerializer):
    parent_network_name = serializers.CharField(source='parent_network.network_name', read_only=True)
    invited_by_username = serializers.CharField(source='invited_by.username', read_only=True)
    method = serializers.SerializerMethodField()
    revenue_split = serializers.SerializerMethodField()
    assigned_partner = serializers.SerializerMethodField()
    user_status = serializers.CharField(read_only=True)

    class Meta:
        model = MCMInvitation
        fields = [
            'id', 'invitation_id', 'child_network_code', 'child_network_name',
            'delegation_type', 'status', 'method', 'revenue_split',
            'parent_network_name', 'invited_by_username', 'created_at', 'expires_at',
            'assigned_partner', 'primary_contact_email','site', 'comments', 'invite_type','user_status',
            'service_account_enabled'
        ]

    def get_method(self, obj):
        return "API" if obj.real_invitation_sent else "Manual"

    def get_revenue_split(self, obj):
        if obj.revenue_share_percentage:
            return f"Parent {obj.revenue_share_percentage}% | Child {obj.child_revenue_percentage}%"
        return "N/A"

    def get_assigned_partner(self, obj):
        from gam_accounts.models import AssignedPartnerChildAccount  # in case of circular imports
        assignment = AssignedPartnerChildAccount.objects.filter(invitation=obj).select_related('partner').first()
        if assignment:
            partner = assignment.partner
            return {
                "id": partner.id,
                "email": partner.email,
                "name": partner.get_full_name() or partner.username
            }
        return None

# NEW: Mark invitation sent serializer
class MarkInvitationSentSerializer(serializers.Serializer):
    """Serializer for marking manual invitation as sent"""
    real_gam_invitation_id = serializers.CharField(
        max_length=100, 
        required=False,
        help_text="Optional: Real GAM invitation ID if known"
    )
    notes = serializers.CharField(
        max_length=500,
        required=False,
        help_text="Optional notes about the manual sending process"
    )

# NEW: MCM invitation analytics serializer
class MCMInvitationAnalyticsSerializer(serializers.Serializer):
    """Serializer for MCM invitation analytics and statistics"""
    total_invitations = serializers.IntegerField()
    pending_invitations = serializers.IntegerField()
    accepted_invitations = serializers.IntegerField()
    declined_invitations = serializers.IntegerField()
    expired_invitations = serializers.IntegerField()
    api_success_rate = serializers.FloatField()
    manual_invitations = serializers.IntegerField()
    api_invitations = serializers.IntegerField()
    delegation_type_breakdown = serializers.DictField()
    recent_invitations = MCMInvitationListSerializer(many=True)

class NetworkSyncSerializer(serializers.Serializer):
    """Serializer for network sync operations"""
    network_code = serializers.CharField(max_length=20, required=False)
    sync_type = serializers.ChoiceField(
        choices=[('parent', 'Parent Network'), ('child', 'Child Network'), ('all', 'All Networks')],
        default='parent'
    )

class NetworkStatsSerializer(serializers.Serializer):
    """Serializer for network statistics"""
    total_networks = serializers.IntegerField()
    parent_networks = serializers.IntegerField()
    child_networks = serializers.IntegerField()
    active_networks = serializers.IntegerField()
    pending_invitations = serializers.IntegerField()
    total_invitations = serializers.IntegerField()
    networks_by_currency = serializers.DictField()
    recent_activity = serializers.ListField()
    
class AssignPartnerToChildSerializer(serializers.Serializer):
    partner_id = serializers.IntegerField()
    invitation_id = serializers.IntegerField()

    def validate(self, attrs):
        partner_id = attrs.get("partner_id")
        invitation_id = attrs.get("invitation_id")

        try:
            partner = User.objects.get(id=partner_id, role='partner')
        except User.DoesNotExist:
            raise serializers.ValidationError("Partner user not found.")

        try:
            invitation = MCMInvitation.objects.get(id=invitation_id)
        except MCMInvitation.DoesNotExist:
            raise serializers.ValidationError("MCM Invitation not found.")

        if AssignedPartnerChildAccount.objects.filter(partner=partner, invitation=invitation).exists():
            raise serializers.ValidationError("This child account is already assigned to this partner.")

        attrs["partner"] = partner
        attrs["invitation"] = invitation
        return attrs
    

class AddChildAccountSerializer(serializers.ModelSerializer):
    site = serializers.CharField(required=False, allow_blank=True)
    comments = serializers.CharField(required=False, allow_blank=True)

    class Meta:
        model = MCMInvitation
        fields = [
            'parent_network', 'child_network_code', 'child_network_name',
            'primary_contact_email', 'delegation_type', 'revenue_share_percentage',
            'site', 'comments'
        ]

    def validate(self, data):
        # Validate if child is already connected
        if GAMNetwork.objects.filter(network_code=data['child_network_code'], parent_network__isnull=False).exists():
            raise serializers.ValidationError("This network is already connected to a parent.")

        # Validate if already invited
        if MCMInvitation.objects.filter(
            child_network_code=data['child_network_code'],
            status__in=['pending', 'awaiting_manual_send']
        ).exists():
            raise serializers.ValidationError("There's already a pending invitation for this network.")

        # Revenue % is mandatory for MANAGE_ACCOUNT
        if data['delegation_type'] == 'MANAGE_ACCOUNT':
            if data.get('revenue_share_percentage') is None:
                raise serializers.ValidationError({
                    'revenue_share_percentage': 'Required for MANAGE_ACCOUNT delegation.'
                })
        elif data['delegation_type'] == 'MANAGE_INVENTORY':
            data.pop('revenue_share_percentage', None)

        return data

    def create(self, validated_data):
        import time
        
        # Generate a unique invitation_id for manual entries
        parent_network = validated_data['parent_network']
        child_network_code = validated_data['child_network_code']
        timestamp = int(time.time())
        
        # Create a unique invitation ID for manual entries
        invitation_id = f"manual_{parent_network.network_code}_{child_network_code}_{timestamp}"
        
        validated_data["invitation_id"] = invitation_id
        validated_data["invite_type"] = "own"         # not an API invite
        validated_data["status"] = "accepted"         # optionally mark as accepted immediately
        validated_data["real_invitation_sent"] = False  # Since it's manual
        
        return MCMInvitation.objects.create(**validated_data)

class MCMInvitationUserStatusUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = MCMInvitation
        fields = ["user_status"]  # allow updating this

class MCMInvitationUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = MCMInvitation
        fields = ['child_network_name', 'site']


class ParentGAMUserCreateSerializer(serializers.ModelSerializer):
    """
    Serializer for creating parent GAM users with minimal required fields
    """
    password = serializers.CharField(write_only=True, min_length=8)
    
    class Meta:
        model = User
        fields = ['email', 'password', 'company_name']
        extra_kwargs = {
            'email': {'required': True},
            'company_name': {'required': True},
        }
    
    def validate_email(self, value):
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("A user with this email address already exists.")
        return value.lower()
    
    def create(self, validated_data):
        # Generate username from email
        username = validated_data['email']
        
        # Create user with minimal required fields
        user = User.objects.create_user(
            username=username,
            email=validated_data['email'],
            password=validated_data['password'],
            first_name='Parent',  # Default first name
            last_name='User',     # Default last name
            company_name=validated_data['company_name'],
            role='parent',
            status='active'
        )
        
        return user