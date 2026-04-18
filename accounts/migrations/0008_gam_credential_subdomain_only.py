"""
Migration: GAMCredential model + subdomain-only TrackingAssignment.
1. Create GAMCredential table
2. Migrate existing partners with network_id → GAMCredential
3. Migrate TrackingAssignment: copy tracking_value → subdomain, drop old columns
4. Remove User.gam_type and User.tracking_method fields
"""
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def migrate_existing_credentials(apps, schema_editor):
    """Create GAMCredential for each partner_admin that has a network_id set."""
    User = apps.get_model('accounts', 'User')
    GAMCredential = apps.get_model('accounts', 'GAMCredential')

    partners = User.objects.filter(
        role='partner_admin',
    ).exclude(network_id='').exclude(network_id__isnull=True)

    for partner in partners:
        GAMCredential.objects.get_or_create(
            partner_admin=partner,
            defaults={
                'auth_method': 'service_account',
                'network_code': partner.network_id,
                'is_connected': True,
            },
        )


def migrate_tracking_to_subdomain(apps, schema_editor):
    """Copy tracking_value → subdomain for all existing TrackingAssignments."""
    TrackingAssignment = apps.get_model('accounts', 'TrackingAssignment')
    for ta in TrackingAssignment.objects.all():
        ta.subdomain = ta.tracking_value or ''
        ta.save(update_fields=['subdomain'])


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0007_remove_publisher_role'),
    ]

    operations = [
        # 1. Create GAMCredential model
        migrations.CreateModel(
            name='GAMCredential',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('auth_method', models.CharField(
                    choices=[('service_account', 'Shared Service Account'), ('oauth2', 'OAuth 2.0')],
                    default='service_account',
                    max_length=20,
                )),
                ('network_code', models.CharField(help_text="Partner's GAM network code", max_length=50)),
                ('oauth_refresh_token', models.TextField(blank=True, help_text='Encrypted OAuth 2.0 refresh token')),
                ('oauth_client_id', models.CharField(blank=True, max_length=255)),
                ('is_connected', models.BooleanField(default=False)),
                ('last_synced_at', models.DateTimeField(blank=True, null=True)),
                ('connection_error', models.TextField(blank=True)),
                ('partner_admin', models.OneToOneField(
                    limit_choices_to={'role': 'partner_admin'},
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='gam_credential',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'db_table': 'accounts_gam_credential',
                'verbose_name': 'GAM Credential',
                'verbose_name_plural': 'GAM Credentials',
            },
        ),

        # 2. Add subdomain column to TrackingAssignment (before data migration)
        migrations.AddField(
            model_name='trackingassignment',
            name='subdomain',
            field=models.CharField(
                blank=True, default='', max_length=255,
                help_text="Subdomain for attribution (e.g. 'creator1.example.com')",
            ),
        ),

        # 3. Migrate existing partner credentials
        migrations.RunPython(
            migrate_existing_credentials,
            reverse_code=migrations.RunPython.noop,
        ),

        # 4. Migrate tracking_value → subdomain
        migrations.RunPython(
            migrate_tracking_to_subdomain,
            reverse_code=migrations.RunPython.noop,
        ),

        # 5. Remove old fields from TrackingAssignment
        migrations.RemoveConstraint(
            model_name='trackingassignment',
            name='valid_tracking_type',
        ),
        migrations.AlterUniqueTogether(
            name='trackingassignment',
            unique_together=set(),
        ),
        migrations.RemoveIndex(
            model_name='trackingassignment',
            name='accounts_tr_trackin_0852e0_idx',
        ),
        migrations.RemoveField(
            model_name='trackingassignment',
            name='tracking_type',
        ),
        migrations.RemoveField(
            model_name='trackingassignment',
            name='tracking_value',
        ),

        # 6. Set up new unique_together and index for subdomain
        migrations.AlterUniqueTogether(
            name='trackingassignment',
            unique_together={('partner_admin', 'subdomain')},
        ),
        migrations.AddIndex(
            model_name='trackingassignment',
            index=models.Index(fields=['subdomain'], name='accounts_tra_subdoma_idx'),
        ),

        # 7. Remove User.gam_type and User.tracking_method fields
        migrations.RemoveField(
            model_name='user',
            name='gam_type',
        ),
        migrations.RemoveField(
            model_name='user',
            name='tracking_method',
        ),
    ]
