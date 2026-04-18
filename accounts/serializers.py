"""
Enhanced serializers for GAM Platform user management
"""
from rest_framework import serializers
from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from django.core.validators import RegexValidator
import logging

from core.models import StatusChoices
from .models import User, PublisherPermission, TrackingAssignment, Subdomain, Tutorial, GAMCredential
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
        help_text="List of permission dicts."
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
            'email_notifications',
            'slack_notifications',
            'slack_webhook_url'
        ]
        extra_kwargs = {
            'email': {'required': True},
            'first_name': {'required': True},
            'last_name': {'required': True},
            'company_name': {'required': False, 'allow_blank': True},
            'role': {'default': User.UserRole.PARTNER_ADMIN}
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

        # Partner admins are active by default
        if user.role == User.UserRole.PARTNER_ADMIN:
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
        fields = ['permission']


class PublisherSiteMiniSerializer(serializers.ModelSerializer):
    class Meta:
        from .models import Site
        model = Site
        fields = ['id', 'url', 'gam_status', 'ads_txt_status']


class PublisherListSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(source='get_full_name', read_only=True)
    gam_connected = serializers.SerializerMethodField()
    gam_network_code = serializers.SerializerMethodField()
    gam_auth_method = serializers.SerializerMethodField()
    sites = PublisherSiteMiniSerializer(many=True, read_only=True)

    def get_gam_connected(self, obj):
        try:
            return obj.gam_credential.is_connected
        except Exception:
            return False

    def get_gam_network_code(self, obj):
        try:
            return obj.gam_credential.network_code
        except Exception:
            return ''

    def get_gam_auth_method(self, obj):
        try:
            return obj.gam_credential.get_auth_method_display()
        except Exception:
            return ''

    class Meta:
        model = User
        fields = ['id', 'company_name', 'first_name', 'last_name', 'full_name', 'email', 'phone_number', 'status', 'date_joined', 'revenue_share_percentage', 'site_url', 'gam_connected', 'gam_network_code', 'gam_auth_method', 'sites']


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


# ---------------------------------------------------------------------------
# Sub-Publisher Serializers
# ---------------------------------------------------------------------------

class SubPublisherListSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(source='get_full_name', read_only=True)
    tracking_info = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            'id', 'email', 'username', 'first_name', 'last_name', 'full_name',
            'phone_number', 'company_name', 'status',
            'custom_fee_percentage', 'date_joined', 'tracking_info',
        ]

    def get_tracking_info(self, obj):
        try:
            ta = obj.tracking_assignment
            return {
                'subdomain': ta.subdomain,
                'is_active': ta.is_active,
            }
        except TrackingAssignment.DoesNotExist:
            return None


class SubPublisherCreateSerializer(serializers.Serializer):
    email = serializers.EmailField()
    first_name = serializers.CharField(max_length=30)
    last_name = serializers.CharField(max_length=30, required=False, allow_blank=True)
    phone_number = serializers.CharField(max_length=20, required=False, allow_blank=True)
    company_name = serializers.CharField(max_length=100, required=False, allow_blank=True)
    subdomain = serializers.CharField(max_length=255)
    custom_fee_percentage = serializers.DecimalField(
        max_digits=5, decimal_places=2, default=0, min_value=0, max_value=100,
    )

    def validate_email(self, value):
        value = value.lower()
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return value

    def validate_subdomain(self, value):
        value = value.strip().lower()
        if not value:
            raise serializers.ValidationError("Subdomain is required.")
        return value

    def create(self, validated_data):
        partner = self.context['request'].user
        email = validated_data['email']
        username = email.split('@')[0]
        base_username = username
        counter = 1
        while User.objects.filter(username=username).exists():
            username = f"{base_username}{counter}"
            counter += 1

        import secrets
        temp_password = secrets.token_urlsafe(16)

        sub_pub = User.objects.create_user(
            username=username,
            email=email,
            first_name=validated_data['first_name'],
            last_name=validated_data.get('last_name', ''),
            phone_number=validated_data.get('phone_number', ''),
            company_name=validated_data.get('company_name', ''),
            role=User.UserRole.SUB_PUBLISHER,
            parent_publisher=partner,
            custom_fee_percentage=validated_data.get('custom_fee_percentage', 0),
            status=StatusChoices.ACTIVE,
            password=temp_password,
        )

        TrackingAssignment.objects.create(
            sub_publisher=sub_pub,
            partner_admin=partner,
            subdomain=validated_data['subdomain'],
        )

        try:
            send_welcome_email_with_reset_link(sub_pub)
        except Exception as e:
            logger.error(f"Welcome email failed for sub-publisher {sub_pub.email}: {e}")

        return sub_pub


class SubPublisherUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = [
            'first_name', 'last_name', 'phone_number', 'company_name',
            'custom_fee_percentage', 'status',
        ]

    def validate_custom_fee_percentage(self, value):
        if value < 0 or value > 100:
            raise serializers.ValidationError("Fee must be between 0 and 100.")
        return value


class TrackingAssignmentSerializer(serializers.ModelSerializer):
    sub_publisher_email = serializers.EmailField(source='sub_publisher.email', read_only=True)

    class Meta:
        model = TrackingAssignment
        fields = [
            'id', 'sub_publisher', 'sub_publisher_email', 'partner_admin',
            'subdomain', 'is_active', 'notes',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'sub_publisher', 'partner_admin', 'created_at', 'updated_at']


class TrackingAssignmentCreateSerializer(serializers.Serializer):
    subdomain = serializers.CharField(max_length=255)
    notes = serializers.CharField(required=False, allow_blank=True, default='')

    def validate_subdomain(self, value):
        value = value.strip().lower()
        if not value:
            raise serializers.ValidationError("Subdomain is required.")
        return value


class GAMCredentialSerializer(serializers.ModelSerializer):
    service_account_email = serializers.CharField(read_only=True)

    class Meta:
        model = GAMCredential
        fields = [
            'id', 'auth_method', 'network_code', 'is_connected',
            'last_synced_at', 'connection_error', 'service_account_email',
            'created_at', 'updated_at',
        ]
        read_only_fields = [
            'id', 'is_connected', 'last_synced_at', 'connection_error',
            'service_account_email', 'created_at', 'updated_at',
        ]


class GAMConnectSerializer(serializers.Serializer):
    network_code = serializers.CharField(max_length=50)
    auth_method = serializers.ChoiceField(
        choices=GAMCredential.AuthMethod.choices,
        default=GAMCredential.AuthMethod.SERVICE_ACCOUNT,
    )

    def validate_network_code(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Network code is required.")
        if not value.isdigit():
            raise serializers.ValidationError("Network code must be numeric.")
        return value


class SubdomainSerializer(serializers.ModelSerializer):
    full_domain = serializers.CharField(read_only=True)
    assigned_to_email = serializers.EmailField(source='assigned_to.email', read_only=True, default=None)

    class Meta:
        model = Subdomain
        fields = [
            'id', 'partner_admin', 'subdomain', 'base_domain', 'full_domain',
            'assigned_to', 'assigned_to_email', 'is_active', 'dns_verified',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'partner_admin', 'full_domain', 'created_at', 'updated_at']


class TutorialSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tutorial
        fields = [
            'id', 'title', 'slug', 'category', 'content', 'summary',
            'order', 'is_published', 'target_roles', 'video_url',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class TutorialListSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tutorial
        fields = [
            'id', 'title', 'slug', 'category', 'summary', 'order',
            'is_published', 'target_roles', 'video_url',
        ]

