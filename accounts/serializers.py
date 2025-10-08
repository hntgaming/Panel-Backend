"""
Enhanced serializers for GAM Platform user management
"""
from rest_framework import serializers
from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from django.core.validators import RegexValidator

from core.models import StatusChoices
from .models import User, PublisherPermission
from .services import send_welcome_email_with_reset_link

class UserRegistrationSerializer(serializers.ModelSerializer):
    username = serializers.CharField(
        max_length=150,
        validators=[],  # Remove default Django username validators
        help_text="Username can contain letters, numbers, spaces, and @/./+/-/_ characters."
    )
    password = serializers.CharField(
        write_only=True,
        validators=[validate_password],
        style={'input_type': 'password'}
    )
    password_confirm = serializers.CharField(
        write_only=True,
        style={'input_type': 'password'}
    )
    phone_number = serializers.CharField(
        max_length=20,
        required=False,
        allow_blank=True,
        validators=[
            RegexValidator(
                regex=r'^\+?1?\d{9,15}$',
                message="Phone number must be in format: '+999999999'. Up to 15 digits allowed."
            )
        ]
    )

    permissions = serializers.ListField(
        child=serializers.DictField(),
        required=False,
        help_text="List of permission dicts. Use 'parent_gam_network' for manage_mcm_invites."
    )

    class Meta:
        model = User
        fields = [
            'email',
            'username',
            'first_name',
            'last_name',
            'password',
            'password_confirm',
            'phone_number',
            'company_name',
            'role',
            'permissions',
            'revenue_share_percentage',
            'site_url',
            'network_id',
            'email_notifications',
            'slack_notifications',
            'slack_webhook_url'
        ]
        extra_kwargs = {
            'email': {'required': True},
            'first_name': {'required': True},
            'last_name': {'required': True},
            'company_name': {'required': False, 'allow_blank': True},
            'role': {'default': User.UserRole.PUBLISHER}
        }

    def validate_email(self, value):
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("A user with this email address already exists.")
        return value.lower()

    def validate_username(self, value):
        # Check for existing username (case-insensitive)
        if User.objects.filter(username__iexact=value).exists():
            raise serializers.ValidationError("A user with this username already exists.")
        
        # Check minimum length
        if len(value) < 3:
            raise serializers.ValidationError("Username must be at least 3 characters long.")
        
        # Custom validation for allowed characters (optional)
        # Allow letters, numbers, spaces, and @.+-_ characters
        import re
        if not re.match(r'^[a-zA-Z0-9\s@.+\-_]+$', value):
            raise serializers.ValidationError(
                "Username can only contain letters, numbers, spaces, and @/./+/-/_ characters."
            )
        
        # Optional: Trim whitespace from beginning and end
        value = value.strip()
        
        # Optional: Ensure username doesn't start or end with spaces
        if value != value.strip():
            raise serializers.ValidationError("Username cannot start or end with spaces.")
        
        # Optional: Prevent multiple consecutive spaces
        if '  ' in value:
            raise serializers.ValidationError("Username cannot contain multiple consecutive spaces.")
        
        return value.lower()

    def validate_role(self, value):
        request = self.context.get('request')
        if value == User.UserRole.ADMIN:
            if User.objects.filter(role=User.UserRole.ADMIN).count() == 0:
                return value
            if not request or not request.user.is_authenticated:
                raise serializers.ValidationError("Admin role can only be assigned by authenticated admins.")
            if not request.user.is_admin_user:
                raise serializers.ValidationError("Only admin users can create other admin users.")
        return value

    def validate_permissions(self, value):
        valid_permissions = dict(PublisherPermission.PermissionChoices.choices).keys()

        for item in value:
            if not isinstance(item, dict):
                raise serializers.ValidationError("Each permission must be a dictionary.")
            if 'permission' not in item:
                raise serializers.ValidationError("Each permission must include 'permission'.")
            if item['permission'] not in valid_permissions:
                raise serializers.ValidationError(f"Invalid permission: {item['permission']}")

            if item['permission'] == 'mcm_invites' and 'parent_gam_network' not in item:
                raise serializers.ValidationError("parent_gam_network is required for mcm_invites.")

        return value

    def validate(self, attrs):
        if attrs.get('password') != attrs.get('password_confirm'):
            raise serializers.ValidationError({
                'password_confirm': "Password confirmation doesn't match password."
            })
        return attrs

    def create(self, validated_data):
        permissions_data = validated_data.pop('permissions', [])
        validated_data.pop('password_confirm')

        validated_data['email'] = validated_data['email'].lower()
        validated_data['username'] = validated_data['username'].lower()

        user = User.objects.create_user(**validated_data)

        # Publishers are active by default
        if user.role == User.UserRole.PUBLISHER:
            user.status = StatusChoices.ACTIVE
            user.save(update_fields=['status'])

            for item in permissions_data:
                permission = item['permission']
                parent_network = None

                if permission == 'manage_mcm_invites':
                    from gam_accounts.models import GAMNetwork
                    try:
                        parent_network = GAMNetwork.objects.get(
                            id=item['parent_gam_network'], network_type='parent'
                        )
                    except GAMNetwork.DoesNotExist:
                        raise serializers.ValidationError({
                            "permissions": [f"Invalid parent_gam_network ID: {item['parent_gam_network']}"]
                        })

                PublisherPermission.objects.create(
                    user=user,
                    permission=permission,
                    parent_gam_network=parent_network
                )

            send_welcome_email_with_reset_link(user)

        return user

class UserLoginSerializer(serializers.Serializer):
    """Enhanced login serializer with role-based validation"""
    email = serializers.EmailField(help_text="Enter your email address")
    password = serializers.CharField(
        write_only=True,
        style={'input_type': 'password'},
        help_text="Enter your password"
    )
    
    def validate_email(self, value):
        """Normalize email to lowercase"""
        return value.lower()
    
    def validate(self, attrs):
        """Validate user credentials with detailed error messages"""
        email = attrs.get('email')
        password = attrs.get('password')
        
        if not email or not password:
            raise serializers.ValidationError("Both email and password are required.")
        
        if not User.objects.filter(email=email).exists():
            raise serializers.ValidationError("No account found with this email address.")
        
        user = authenticate(
            request=self.context.get('request'),
            username=email,
            password=password
        )
        
        if not user:
            raise serializers.ValidationError("Invalid email or password.")

        if not user.is_active:
            raise serializers.ValidationError("This account has been deactivated. Please contact support.")

        if user.status != StatusChoices.ACTIVE:
            raise serializers.ValidationError(
                f"Account status is '{user.status}'. Please contact support."
            )
        
        attrs['user'] = user
        return attrs

class UserProfileSerializer(serializers.ModelSerializer):
    """Complete user profile serializer with role information"""
    full_name = serializers.CharField(source='get_full_name', read_only=True)
    is_active_user = serializers.BooleanField(read_only=True)
    is_admin_user = serializers.BooleanField(read_only=True)
    is_partner_user = serializers.BooleanField(read_only=True)
    role_display = serializers.CharField(source='get_role_display', read_only=True)
    
    class Meta:
        model = User
        fields = [
            'id',
            'email',
            'username',
            'first_name',
            'last_name',
            'full_name',
            'phone_number',
            'company_name',
            'role',
            'role_display',
            'is_admin_user',
            'is_partner_user',
            'email_notifications',
            'slack_notifications',
            'slack_webhook_url',
            'status',
            'is_active_user',
            'date_joined',
            'last_login',
            'last_login_ip'
        ]
        read_only_fields = [
            'id', 
            'email',  
            'username',  
            'role',  # Role changes should be done by admin separately
            'status',  
            'date_joined', 
            'last_login',
            'last_login_ip'
        ]
    
    def validate_phone_number(self, value):
        """Validate phone number format"""
        if value:
            import re
            if not re.match(r'^\+?1?\d{9,15}$', value):
                raise serializers.ValidationError(
                    "Phone number must be in format: '+999999999'. Up to 15 digits allowed."
                )
        return value


class UserRoleUpdateSerializer(serializers.ModelSerializer):
    """Serializer for admin users to update user roles"""
    
    class Meta:
        model = User
        fields = ['role', 'status']
    
    def validate(self, attrs):
        """Only admins can update roles"""
        request = self.context.get('request')
        
        if not request or not request.user.is_authenticated:
            raise serializers.ValidationError(
                "Authentication required to update user roles."
            )
        
        if not request.user.is_admin_user:
            raise serializers.ValidationError(
                "Only admin users can update user roles and status."
            )
        
        return attrs


class ChangePasswordSerializer(serializers.Serializer):
    """Serializer for password change"""
    old_password = serializers.CharField(
        write_only=True,
        style={'input_type': 'password'}
    )
    new_password = serializers.CharField(
        write_only=True,
        validators=[validate_password],
        style={'input_type': 'password'}
    )
    confirm_password = serializers.CharField(
        write_only=True,
        style={'input_type': 'password'}
    )
    
    def validate_old_password(self, value):
        """Check old password is correct"""
        user = self.context['request'].user
        if not user.check_password(value):
            raise serializers.ValidationError("Old password is incorrect.")
        return value
    
    def validate(self, attrs):
        """Check new passwords match"""
        if attrs['new_password'] != attrs['confirm_password']:
            raise serializers.ValidationError({
                'confirm_password': "New password confirmation doesn't match."
            })
        return attrs
    
    def save(self):
        """Update user password"""
        from django.utils import timezone
        
        user = self.context['request'].user
        user.set_password(self.validated_data['new_password'])
        user.password_changed_at = timezone.now()
        user.save()
        return user
    

class PublisherPermissionSerializer(serializers.ModelSerializer):
    class Meta:
        model = PublisherPermission
        fields = ['permission', 'parent_gam_network']


class PublisherListSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'company_name', 'email', 'status', 'date_joined', 'revenue_share_percentage', 'site_url', 'network_id']

