# Generated manually for adding publisher fields

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='revenue_share_percentage',
            field=models.DecimalField(decimal_places=2, default=10.0, help_text='Percentage of revenue that goes to the parent network (0-100%)', max_digits=5),
        ),
        migrations.AddField(
            model_name='user',
            name='site_url',
            field=models.URLField(blank=True, help_text="Publisher's website URL"),
        ),
        migrations.AddField(
            model_name='user',
            name='network_id',
            field=models.CharField(blank=True, help_text="Publisher's GAM network ID", max_length=50),
        ),
    ]
