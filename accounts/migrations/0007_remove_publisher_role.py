"""
Migration to remove the 'publisher' role entirely.
- Converts all existing users with role='publisher' to role='partner_admin'
- Updates model field choices, defaults, and limit_choices_to constraints
"""
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def migrate_publisher_to_partner_admin(apps, schema_editor):
    """Convert all users with role='publisher' to role='partner_admin'."""
    User = apps.get_model('accounts', 'User')
    updated = User.objects.filter(role='publisher').update(role='partner_admin')
    if updated:
        print(f"\n  Migrated {updated} user(s) from 'publisher' to 'partner_admin'")


def reverse_migrate(apps, schema_editor):
    """Reverse is a no-op — we cannot know which partner_admins were formerly publishers."""
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0006_partner_dashboard_models'),
        ('accounts', '0006_partner_dashboard_fixes'),
    ]

    operations = [
        # 1. Data migration: convert publisher -> partner_admin
        migrations.RunPython(migrate_publisher_to_partner_admin, reverse_migrate),

        # 2. Update User.role field: remove publisher from choices, change default
        migrations.AlterField(
            model_name='user',
            name='role',
            field=models.CharField(
                choices=[
                    ('admin', 'Admin User'),
                    ('partner_admin', 'Partner Admin'),
                    ('sub_publisher', 'Sub-Publisher (Creator/Traffic Partner)'),
                ],
                default='partner_admin',
                help_text='Admin: Full access. Partner-Admin: Connects GAM & manages sub-publishers. Sub-Publisher: Creator/traffic partner.',
                max_length=20,
            ),
        ),

        # 3. Update PublisherAccountAccess.publisher limit_choices_to
        migrations.AlterField(
            model_name='publisheraccountaccess',
            name='publisher',
            field=models.ForeignKey(
                blank=True,
                limit_choices_to={'role': 'partner_admin'},
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='assigned_accounts',
                to=settings.AUTH_USER_MODEL,
            ),
        ),

        # 4. Update PaymentDetail.user limit_choices_to
        migrations.AlterField(
            model_name='paymentdetail',
            name='user',
            field=models.OneToOneField(
                help_text='Partner admin or sub-publisher user',
                limit_choices_to={'role__in': ['partner_admin', 'sub_publisher']},
                on_delete=django.db.models.deletion.CASCADE,
                related_name='payment_details',
                to=settings.AUTH_USER_MODEL,
            ),
        ),

        # 5. Update Site.publisher limit_choices_to
        migrations.AlterField(
            model_name='site',
            name='publisher',
            field=models.ForeignKey(
                help_text='Partner admin who owns this site',
                limit_choices_to={'role': 'partner_admin'},
                on_delete=django.db.models.deletion.CASCADE,
                related_name='sites',
                to='accounts.user',
            ),
        ),
    ]
