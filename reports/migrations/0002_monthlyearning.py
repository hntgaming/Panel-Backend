from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('reports', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='MonthlyEarning',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('month', models.DateField(help_text='First day of the month, e.g. 2026-03-01')),
                ('gross_revenue', models.DecimalField(decimal_places=2, default=0, max_digits=20)),
                ('total_impressions', models.BigIntegerField(default=0)),
                ('ivt_deduction', models.DecimalField(decimal_places=2, default=0, max_digits=20)),
                ('parent_share', models.DecimalField(decimal_places=2, default=0, max_digits=20)),
                ('net_earnings', models.DecimalField(decimal_places=2, default=0, max_digits=20)),
                ('status', models.CharField(choices=[('pending', 'Pending'), ('processing', 'Processing'), ('paid', 'Paid')], default='pending', max_length=20)),
                ('notes', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('publisher', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='earnings', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'db_table': 'report_monthly_earnings',
                'ordering': ['-month', 'publisher__email'],
                'unique_together': {('publisher', 'month')},
                'indexes': [
                    models.Index(fields=['publisher', '-month'], name='report_mont_publish_idx'),
                    models.Index(fields=['status'], name='report_mont_status_idx'),
                ],
            },
        ),
    ]
