"""
Update Property.publisher limit_choices_to after publisher role removal.
"""
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('reports', '0006_sub_publisher_earning'),
        ('reports', '0006_partner_dashboard_models'),
        ('accounts', '0007_remove_publisher_role'),
    ]

    operations = [
        migrations.AlterField(
            model_name='property',
            name='publisher',
            field=models.ForeignKey(
                limit_choices_to={'role': 'partner_admin'},
                on_delete=django.db.models.deletion.CASCADE,
                related_name='properties',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]
