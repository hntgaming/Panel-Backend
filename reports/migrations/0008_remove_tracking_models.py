"""
Remove tracking models: Property, Placement, GAMMapping, SourceTypeRule.
The tracking/attribution subsystem has been removed from the application.
"""
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('reports', '0007_remove_publisher_role_from_property'),
    ]

    operations = [
        migrations.DeleteModel(name='SourceTypeRule'),
        migrations.DeleteModel(name='GAMMapping'),
        migrations.DeleteModel(name='Placement'),
        migrations.DeleteModel(name='Property'),
    ]
