"""
Add unified tracking models (Property, Placement, GAMMapping, SourceTypeRule)
and enhance MasterMetaData with property_id, placement_id, source_type, attribution_method.
Backward-compatible: all new fields on MasterMetaData are nullable.
"""

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("reports", "0002_monthlyearning"),
    ]

    operations = [
        # ------------------------------------------------------------------
        # New tracking tables
        # ------------------------------------------------------------------
        migrations.CreateModel(
            name="Property",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("property_id", models.CharField(db_index=True, help_text="Internal property ID, e.g. prop_42_example_com", max_length=100, unique=True)),
                ("domain", models.CharField(blank=True, db_index=True, help_text="Primary domain for web properties", max_length=255)),
                ("app_bundle", models.CharField(blank=True, help_text="App bundle ID for mobile properties", max_length=255)),
                ("platform", models.CharField(choices=[("web", "Web"), ("app", "App"), ("amp", "AMP"), ("ctv", "CTV")], default="web", max_length=10)),
                ("status", models.CharField(choices=[("active", "Active"), ("inactive", "Inactive"), ("pending", "Pending")], default="active", max_length=20)),
                ("notes", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("publisher", models.ForeignKey(limit_choices_to={"role": "publisher"}, on_delete=django.db.models.deletion.CASCADE, related_name="properties", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "db_table": "tracking_properties",
                "verbose_name_plural": "Properties",
            },
        ),
        migrations.AddIndex(
            model_name="property",
            index=models.Index(fields=["publisher", "status"], name="tracking_pr_publish_idx"),
        ),
        migrations.AddIndex(
            model_name="property",
            index=models.Index(fields=["domain"], name="tracking_pr_domain_idx"),
        ),

        migrations.CreateModel(
            name="Placement",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("placement_id", models.CharField(db_index=True, help_text="Internal placement ID", max_length=150, unique=True)),
                ("placement_name", models.CharField(help_text="Human-readable name", max_length=150)),
                ("ad_size", models.CharField(blank=True, help_text="Ad size, e.g. 300x250", max_length=50)),
                ("device_type", models.CharField(choices=[("all", "All"), ("desktop", "Desktop"), ("mobile", "Mobile"), ("tablet", "Tablet")], default="all", max_length=20)),
                ("status", models.CharField(choices=[("active", "Active"), ("inactive", "Inactive"), ("pending", "Pending")], default="active", max_length=20)),
                ("notes", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("property", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="placements", to="reports.property")),
            ],
            options={
                "db_table": "tracking_placements",
            },
        ),
        migrations.AddIndex(
            model_name="placement",
            index=models.Index(fields=["property", "status"], name="tracking_pl_prop_st_idx"),
        ),

        migrations.CreateModel(
            name="GAMMapping",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("gam_network_code", models.CharField(db_index=True, max_length=50)),
                ("gam_ad_unit_path", models.CharField(blank=True, db_index=True, max_length=500)),
                ("gam_ad_unit_id", models.CharField(blank=True, max_length=50)),
                ("gam_line_item_id", models.CharField(blank=True, max_length=50)),
                ("gam_order_id", models.CharField(blank=True, max_length=50)),
                ("source_type", models.CharField(choices=[("mcm_direct", "MCM Direct"), ("gam360_passback", "GAM 360 Passback"), ("prebid", "Prebid"), ("open_bidding", "Open Bidding"), ("adx_direct", "AdX Direct"), ("house", "House"), ("direct_campaign", "Direct Campaign"), ("unknown", "Unknown")], default="unknown", max_length=30)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("publisher", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="gam_mappings", to=settings.AUTH_USER_MODEL)),
                ("property", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="gam_mappings", to="reports.property")),
                ("placement", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="gam_mappings", to="reports.placement")),
            ],
            options={
                "db_table": "tracking_gam_mappings",
            },
        ),
        migrations.AddIndex(
            model_name="gammapping",
            index=models.Index(fields=["gam_ad_unit_path"], name="tracking_gm_aupath_idx"),
        ),
        migrations.AddIndex(
            model_name="gammapping",
            index=models.Index(fields=["gam_ad_unit_id"], name="tracking_gm_auid_idx"),
        ),
        migrations.AddIndex(
            model_name="gammapping",
            index=models.Index(fields=["gam_line_item_id"], name="tracking_gm_li_idx"),
        ),
        migrations.AddIndex(
            model_name="gammapping",
            index=models.Index(fields=["gam_network_code", "gam_ad_unit_path"], name="tracking_gm_net_au_idx"),
        ),
        migrations.AddIndex(
            model_name="gammapping",
            index=models.Index(fields=["source_type"], name="tracking_gm_src_idx"),
        ),

        migrations.CreateModel(
            name="SourceTypeRule",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("priority", models.IntegerField(default=100)),
                ("match_field", models.CharField(choices=[("line_item_name", "Line Item Name"), ("line_item_id", "Line Item ID"), ("order_name", "Order Name"), ("order_id", "Order ID"), ("ad_unit_path", "Ad Unit Path"), ("creative_name", "Creative Name")], max_length=30)),
                ("match_type", models.CharField(choices=[("contains", "Contains"), ("startswith", "Starts With"), ("exact", "Exact Match"), ("regex", "Regex")], default="contains", max_length=20)),
                ("match_value", models.CharField(max_length=500)),
                ("source_type", models.CharField(choices=[("mcm_direct", "MCM Direct"), ("gam360_passback", "GAM 360 Passback"), ("prebid", "Prebid"), ("open_bidding", "Open Bidding"), ("adx_direct", "AdX Direct"), ("house", "House"), ("direct_campaign", "Direct Campaign"), ("unknown", "Unknown")], max_length=30)),
                ("is_active", models.BooleanField(default=True)),
                ("notes", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "db_table": "tracking_source_type_rules",
                "ordering": ["priority"],
            },
        ),

        # ------------------------------------------------------------------
        # Enhance MasterMetaData with unified identity columns
        # ------------------------------------------------------------------
        migrations.AddField(
            model_name="mastermetadata",
            name="property_id_tracking",
            field=models.CharField(blank=True, db_index=True, help_text="Internal property ID from tracking_properties", max_length=100, null=True),
        ),
        migrations.AddField(
            model_name="mastermetadata",
            name="placement_id_tracking",
            field=models.CharField(blank=True, db_index=True, help_text="Internal placement ID from tracking_placements", max_length=150, null=True),
        ),
        migrations.AddField(
            model_name="mastermetadata",
            name="source_type",
            field=models.CharField(blank=True, choices=[("mcm_direct", "MCM Direct"), ("gam360_passback", "GAM 360 Passback"), ("prebid", "Prebid"), ("open_bidding", "Open Bidding"), ("adx_direct", "AdX Direct"), ("house", "House"), ("direct_campaign", "Direct Campaign"), ("unknown", "Unknown")], db_index=True, max_length=30, null=True),
        ),
        migrations.AddField(
            model_name="mastermetadata",
            name="attribution_method",
            field=models.CharField(blank=True, choices=[("key_value", "Key-Value Match"), ("ad_unit_path", "Ad Unit Path Parse"), ("gam_mapping", "GAM Mapping Table"), ("domain_match", "Domain Match"), ("legacy", "Legacy Fallback"), ("unattributed", "Unattributed")], max_length=30, null=True),
        ),

        # Indexes on MasterMetaData new fields
        migrations.AddIndex(
            model_name="mastermetadata",
            index=models.Index(fields=["property_id_tracking", "date"], name="mm_propid_date_idx"),
        ),
        migrations.AddIndex(
            model_name="mastermetadata",
            index=models.Index(fields=["placement_id_tracking", "date"], name="mm_plcid_date_idx"),
        ),
        migrations.AddIndex(
            model_name="mastermetadata",
            index=models.Index(fields=["source_type", "date"], name="mm_srctype_date_idx"),
        ),
        migrations.AddIndex(
            model_name="mastermetadata",
            index=models.Index(fields=["publisher_id", "property_id_tracking", "date"], name="mm_pub_prop_date_idx"),
        ),
    ]
