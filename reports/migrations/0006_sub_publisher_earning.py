from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('accounts', '0005_add_gam_type_to_user'),
        ('reports', '0005_remove_tracking_attribution_fields'),
    ]

    operations = [
        migrations.CreateModel(
            name='SubPublisherEarning',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('date', models.DateField(db_index=True)),
                ('gross_revenue', models.DecimalField(decimal_places=6, default=0, max_digits=20)),
                ('fee_percentage', models.DecimalField(decimal_places=2, default=0, help_text='Fee percentage snapshot at calculation time', max_digits=5)),
                ('fee_amount', models.DecimalField(decimal_places=6, default=0, max_digits=20)),
                ('net_revenue', models.DecimalField(decimal_places=6, default=0, max_digits=20)),
                ('impressions', models.BigIntegerField(default=0)),
                ('clicks', models.BigIntegerField(default=0)),
                ('ecpm', models.DecimalField(decimal_places=2, default=0, max_digits=20)),
                ('source_dimension_type', models.CharField(blank=True, default='', help_text="Dimension type used for matching (e.g. 'site', 'trafficSource')", max_length=32)),
                ('source_dimension_value', models.CharField(blank=True, default='', help_text='Dimension value that matched the tracking assignment', max_length=255)),
                ('calculated_at', models.DateTimeField(auto_now=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('partner_admin', models.ForeignKey(limit_choices_to={'role__in': ['partner_admin', 'admin']}, on_delete=django.db.models.deletion.CASCADE, related_name='managed_sub_publisher_earnings', to=settings.AUTH_USER_MODEL)),
                ('sub_publisher', models.ForeignKey(limit_choices_to={'role': 'sub_publisher'}, on_delete=django.db.models.deletion.CASCADE, related_name='sub_publisher_earnings', to=settings.AUTH_USER_MODEL)),
                ('tracking_assignment', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='earnings', to='accounts.trackingassignment')),
            ],
            options={
                'db_table': 'report_sub_publisher_earnings',
                'ordering': ['-date', 'sub_publisher__email'],
                'unique_together': {('sub_publisher', 'date')},
                'indexes': [
                    models.Index(fields=['sub_publisher', '-date'], name='rpt_spe_subpub_date_idx'),
                    models.Index(fields=['partner_admin', '-date'], name='rpt_spe_partner_date_idx'),
                    models.Index(fields=['date'], name='rpt_spe_date_idx'),
                ],
            },
        ),
    ]
