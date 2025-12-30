# Generated migration for Site model

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0003_add_payment_details'),
    ]

    operations = [
        migrations.CreateModel(
            name='Site',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('url', models.URLField(help_text='Site URL (e.g., https://example.com)')),
                ('gam_status', models.CharField(choices=[('pending', 'Pending'), ('added', 'Added to GAM'), ('failed', 'Failed to Add'), ('not_added', 'Not Added')], default='not_added', help_text='Status of site in GAM', max_length=20)),
                ('gam_site_id', models.CharField(blank=True, help_text='GAM Site ID if added to GAM', max_length=50, null=True)),
                ('ads_txt_status', models.CharField(choices=[('not_verified', 'Not Verified'), ('verified', 'Verified'), ('invalid', 'Invalid'), ('pending', 'Pending Verification')], default='not_verified', help_text='Status of ads.txt verification', max_length=20)),
                ('ads_txt_last_checked', models.DateTimeField(blank=True, help_text='Last time ads.txt was checked', null=True)),
                ('notes', models.TextField(blank=True, help_text='Additional notes about the site')),
                ('publisher', models.ForeignKey(help_text='Publisher who owns this site', limit_choices_to={'role': 'publisher'}, on_delete=django.db.models.deletion.CASCADE, related_name='sites', to='accounts.user')),
            ],
            options={
                'verbose_name': 'Site',
                'verbose_name_plural': 'Sites',
                'db_table': 'accounts_site',
                'ordering': ['-created_at'],
            },
        ),
        migrations.AlterUniqueTogether(
            name='site',
            unique_together={('publisher', 'url')},
        ),
    ]
