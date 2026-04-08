# reports/tracking_serializers.py

from rest_framework import serializers
from .models import Property, Placement, GAMMapping, SourceTypeRule, SOURCE_TYPE_CHOICES


class PlacementInlineSerializer(serializers.ModelSerializer):
    class Meta:
        model = Placement
        fields = ['id', 'placement_id', 'placement_name', 'ad_size', 'device_type', 'status']
        read_only_fields = ['id']


class PropertySerializer(serializers.ModelSerializer):
    publisher_email = serializers.EmailField(source='publisher.email', read_only=True)
    publisher_name = serializers.SerializerMethodField()
    placements = PlacementInlineSerializer(many=True, read_only=True)
    placement_count = serializers.SerializerMethodField()

    class Meta:
        model = Property
        fields = [
            'id', 'publisher', 'publisher_email', 'publisher_name',
            'property_id', 'domain', 'app_bundle', 'platform', 'status',
            'notes', 'placements', 'placement_count',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def get_publisher_name(self, obj):
        return obj.publisher.get_full_name() or obj.publisher.email

    def get_placement_count(self, obj):
        return obj.placements.count()


class PlacementSerializer(serializers.ModelSerializer):
    property_pid = serializers.CharField(source='property.property_id', read_only=True)
    property_domain = serializers.CharField(source='property.domain', read_only=True)
    publisher_email = serializers.SerializerMethodField()

    class Meta:
        model = Placement
        fields = [
            'id', 'property', 'property_pid', 'property_domain',
            'publisher_email',
            'placement_id', 'placement_name', 'ad_size', 'device_type',
            'status', 'notes',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def get_publisher_email(self, obj):
        return obj.property.publisher.email


class GAMMappingSerializer(serializers.ModelSerializer):
    publisher_email = serializers.SerializerMethodField()
    property_pid = serializers.SerializerMethodField()
    placement_pid = serializers.SerializerMethodField()

    class Meta:
        model = GAMMapping
        fields = [
            'id', 'publisher', 'publisher_email',
            'property', 'property_pid',
            'placement', 'placement_pid',
            'gam_network_code', 'gam_ad_unit_path', 'gam_ad_unit_id',
            'gam_line_item_id', 'gam_order_id',
            'source_type', 'is_active',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def get_publisher_email(self, obj):
        return obj.publisher.email if obj.publisher else None

    def get_property_pid(self, obj):
        return obj.property.property_id if obj.property else None

    def get_placement_pid(self, obj):
        return obj.placement.placement_id if obj.placement else None


class SourceTypeRuleSerializer(serializers.ModelSerializer):
    class Meta:
        model = SourceTypeRule
        fields = [
            'id', 'priority', 'match_field', 'match_type', 'match_value',
            'source_type', 'is_active', 'notes', 'created_at',
        ]
        read_only_fields = ['id', 'created_at']


class TagGenerationSerializer(serializers.Serializer):
    network_code = serializers.CharField(max_length=50)
    publisher_id = serializers.IntegerField()
    property_id = serializers.CharField(max_length=100)
    placement_id = serializers.CharField(max_length=150)
    placement_name = serializers.CharField(max_length=150)
    ad_size = serializers.CharField(max_length=100, help_text="e.g. 300x250 or 300x250,728x90")
    source_type = serializers.CharField(max_length=30, required=False, default='mcm_direct')
    env = serializers.CharField(max_length=10, required=False, default='web')
    custom_ad_unit_path = serializers.CharField(max_length=500, required=False, allow_blank=True)
    div_id = serializers.CharField(max_length=100, required=False, allow_blank=True)
    lazy_load = serializers.BooleanField(required=False, default=True)
    collapse_empty = serializers.BooleanField(required=False, default=True)
    domain = serializers.CharField(max_length=255, required=False, allow_blank=True,
                                   help_text="Publisher domain for ad unit path (e.g. example.com)")
    slot_name = serializers.CharField(max_length=150, required=False, allow_blank=True,
                                      help_text="GAM slot name (e.g. Top_Leaderboard_ATF)")


class PassbackTagSerializer(serializers.Serializer):
    network_code = serializers.CharField(max_length=50)
    publisher_id = serializers.IntegerField()
    property_id = serializers.CharField(max_length=100)
    placement_id = serializers.CharField(max_length=150)
    placement_name = serializers.CharField(max_length=150)
    ad_size = serializers.CharField(max_length=100)
    source_type = serializers.CharField(max_length=30, required=False, default='gam360_passback')
    env = serializers.CharField(max_length=10, required=False, default='web')
    custom_ad_unit_path = serializers.CharField(max_length=500, required=False, allow_blank=True)
    domain = serializers.CharField(max_length=255, required=False, allow_blank=True,
                                   help_text="Publisher domain for ad unit path (e.g. example.com)")
    slot_name = serializers.CharField(max_length=150, required=False, allow_blank=True,
                                      help_text="GAM slot name (e.g. Top_Leaderboard_ATF)")
