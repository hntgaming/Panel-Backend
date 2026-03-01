"""
Enhanced serializers for GAM Platform user management
"""
from rest_framework import serializers
from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from django.core.validators import RegexValidator
import logging

from core.models import StatusChoices
from .models import User, PublisherPermission
from .services import send_welcome_email_with_reset_link

logger = logging.getLogger(__name__)

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
                PublisherPermission.objects.create(
                    user=user,
                    permission=permission
                )

            try:
                send_welcome_email_with_reset_link(user)
            except Exception as e:
                logger.error(f"Welcome email failed for {user.email}: {e}")

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
    # Removed is_partner_user - not in User model
    role_display = serializers.SerializerMethodField()
    
    def get_role_display(self, obj):
        """Get human-readable role display"""
        return obj.get_role_display() if hasattr(obj, 'get_role_display') else obj.role.title()
    
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
    full_name = serializers.CharField(source='get_full_name', read_only=True)
    
    class Meta:
        model = User
        fields = ['id', 'company_name', 'first_name', 'last_name', 'full_name', 'email', 'phone_number', 'status', 'date_joined', 'revenue_share_percentage', 'site_url', 'network_id']


class SiteSerializer(serializers.ModelSerializer):
    publisher_email = serializers.EmailField(source='publisher.email', read_only=True)
    publisher_name = serializers.CharField(source='publisher.get_full_name', read_only=True)
    
    class Meta:
        from .models import Site
        model = Site
        fields = [
            'id', 'publisher', 'publisher_email', 'publisher_name', 'url',
            'gam_status', 'gam_site_id', 'ads_txt_status', 'ads_txt_last_checked',
            'notes', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class PaymentDetailSerializer(serializers.ModelSerializer):
    """Serializer for payment details"""
    user_email = serializers.EmailField(source='user.email', read_only=True)
    user_name = serializers.CharField(source='user.get_full_name', read_only=True)
    publisher_name = serializers.CharField(source='user.company_name', read_only=True)
    payment_method_display = serializers.CharField(source='get_payment_method_display', read_only=True)
    
    class Meta:
        from .models import PaymentDetail
        model = PaymentDetail
        fields = [
            'id',
            'user',
            'user_email',
            'user_name',
            'publisher_name',
            'payment_method',
            'payment_method_display',
            'crypto_wallet_address',
            'beneficiary_name',
            'bank_name',
            'iban',
            'swift_code',
            'country',
            'notes',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'user', 'user_email', 'user_name', 'publisher_name', 'payment_method_display', 'created_at', 'updated_at']
    
    def validate(self, data):
        """Validate payment details based on payment method"""
        payment_method = data.get('payment_method')
        
        if payment_method == 'crypto':
            if not data.get('crypto_wallet_address'):
                raise serializers.ValidationError({
                    'crypto_wallet_address': 'Wallet address is required for crypto payments'
                })
        elif payment_method == 'wire':
            required_fields = ['beneficiary_name', 'bank_name', 'iban', 'swift_code', 'country']
            missing = [field for field in required_fields if not data.get(field)]
            if missing:
                raise serializers.ValidationError({
                    field: f'{field.replace("_", " ").title()} is required for wire transfer'
                    for field in missing
                })
        
        return data


class PaymentDetailListSerializer(serializers.ModelSerializer):
    """Simplified serializer for listing payment details (admin view)"""
    user_email = serializers.EmailField(source='user.email', read_only=True)
    publisher_name = serializers.CharField(source='user.company_name', read_only=True)
    payment_method_display = serializers.CharField(source='get_payment_method_display', read_only=True)
    
    class Meta:
        from .models import PaymentDetail
        model = PaymentDetail
        fields = [
            'id',
            'user',
            'user_email',
            'publisher_name',
            'payment_method',
            'payment_method_display',
            'created_at',
            'updated_at',
        ]


class PublicSignupSerializer(serializers.Serializer):
    """
    Public signup serializer for new publishers
    Fields: name, phone (WhatsApp), email, site_link
    Automatically sends MCM invitation via GAM API
    """
    name = serializers.CharField(
        max_length=100,
        help_text="Full name of the publisher"
    )
    phone = serializers.CharField(
        max_length=20,
        validators=[
            RegexValidator(
                regex=r'^\+?1?\d{9,15}$',
                message="Phone number must be in format: '+999999999'. Up to 15 digits allowed."
            )
        ],
        help_text="WhatsApp phone number"
    )
    email = serializers.EmailField(
        help_text="Email address (must not have existing AdSense/AdManager account)"
    )
    site_link = serializers.URLField(
        help_text="Website URL"
    )
    network_id = serializers.CharField(
        max_length=50,
        required=False,
        allow_blank=True,
        help_text="GAM Network ID (optional). If provided, MCM invitation will be sent to this existing network."
    )
    
    def validate_network_id(self, value):
        """Validate network ID format"""
        if not value or not value.strip():
            return None  # Allow empty/blank values
        value = value.strip()
        # Network ID should be numeric
        if not value.isdigit():
            raise serializers.ValidationError(
                "Network ID must be numeric."
            )
        return value
    
    def validate_email(self, value):
        """Check if email already exists"""
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError(
                "A user with this email address already exists. Please use a different email or login."
            )
        return value.lower()
    
    def validate_site_link(self, value):
        """Validate and normalize site link"""
        # Ensure URL has protocol
        value = value.strip()
        if not value.startswith('http://') and not value.startswith('https://'):
            value = f'https://{value}'
        # Remove trailing slash for consistency
        if value.endswith('/'):
            value = value[:-1]
        return value
    
    def create(self, validated_data):
        """Create user and send MCM invitation"""
        from reports.gam_client import GAMClientService
        from core.models import StatusChoices
        
        # Extract data
        name = validated_data['name']
        phone = validated_data['phone']
        email = validated_data['email']
        site_link = validated_data['site_link']
        network_id = validated_data.get('network_id', '').strip() if validated_data.get('network_id') else None
        
        # Parse name into first_name and last_name
        name_parts = name.strip().split(maxsplit=1)
        first_name = name_parts[0] if name_parts else name
        last_name = name_parts[1] if len(name_parts) > 1 else ""
        
        # Generate username from email
        username = email.split('@')[0]
        # Ensure username is unique
        base_username = username
        counter = 1
        while User.objects.filter(username=username).exists():
            username = f"{base_username}{counter}"
            counter += 1
        
        # Create user with temporary password (will be set via welcome email)
        import secrets
        temp_password = secrets.token_urlsafe(16)
        
        # Create user with network_id (if provided)
        user_kwargs = {
            'username': username,
            'email': email,
            'first_name': first_name,
            'last_name': last_name,
            'phone_number': phone,
            'site_url': validated_data['site_link'],  # Store original URL with https
            'role': User.UserRole.PUBLISHER,
            'status': StatusChoices.PENDING_APPROVAL,  # Will be activated after password reset
            'password': temp_password,
            'revenue_share_percentage': 20.00,  # 80% to publisher, 20% to parent
        }
        
        # Only add network_id if provided
        if network_id:
            user_kwargs['network_id'] = network_id
        
        user = User.objects.create_user(**user_kwargs)
        
        # Create child network name: site link without https + "PubDash" (for GAM)
        # Remove https:// or http://
        site_name = validated_data['site_link']
        if site_name.startswith('https://'):
            site_name = site_name[8:]
        elif site_name.startswith('http://'):
            site_name = site_name[7:]
        # Remove trailing slash
        if site_name.endswith('/'):
            site_name = site_name[:-1]
        # Remove www. if present
        if site_name.startswith('www.'):
            site_name = site_name[4:]
        
        child_network_name = f"{site_name} - PubDash"
        
        # Send MCM invitation via GAM API
        # Use network_id as child_network_code if provided (existing network), otherwise None (new network)
        mcm_result = GAMClientService.send_mcm_invitation(
            email=email,
            child_network_name=child_network_name,
            child_network_code=network_id,  # None for new network, network_id for existing
            revenue_share_percentage=None,  # Not required for managed inventory
            delegation_type='MANAGE_INVENTORY'
        )
        
        if not mcm_result.get('success'):
            # If MCM invitation fails, still create user but log the error
            # User can be manually set up later
            logger.warning(f"⚠️ User created but MCM invitation failed: {mcm_result.get('error')}")
            # Don't raise exception - allow user creation to proceed
            # Admin can manually send invitation later
        
        # Add site to parent GAM network
        # Extract domain from site_link for site name
        site_name = validated_data['site_link']
        if site_name.startswith('https://'):
            site_name = site_name[8:]
        elif site_name.startswith('http://'):
            site_name = site_name[7:]
        if site_name.endswith('/'):
            site_name = site_name[:-1]
        if site_name.startswith('www.'):
            site_name = site_name[4:]
        
        site_result = GAMClientService.add_site_to_parent_network(
            site_url=validated_data['site_link'],
            site_name=site_name,
            child_network_code=network_id if network_id else None
        )
        
        if not site_result.get('success'):
            # If site addition fails, log but don't fail user creation
            logger.warning(f"Site could not be added to GAM: {site_result.get('error')}")
        else:
            logger.debug(f"Site added to parent GAM network: {site_result.get('site_url')}")
        
        # Send welcome email with password reset link
        send_welcome_email_with_reset_link(user)
        
        # Assign default permissions (reports and settings)
        PublisherPermission.objects.create(user=user, permission='reports')
        PublisherPermission.objects.create(user=user, permission='settings')
        
        # Create Site record
        from .models import Site
        site = Site.objects.create(
            publisher=user,
            url=validated_data['site_link'],
            gam_status=Site.GamStatus.GETTING_READY if site_result.get('success') else Site.GamStatus.NEEDS_ATTENTION,
            gam_site_id=site_result.get('site_id') if site_result.get('success') else None,
            ads_txt_status=Site.AdsTxtStatus.MISSING
        )
        
        return user

