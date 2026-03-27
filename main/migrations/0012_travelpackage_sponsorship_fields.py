# Generated manually because full Django startup is unavailable in this environment.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("main", "0011_merge_20260327_1323"),
    ]

    operations = [
        migrations.AddField(
            model_name="travelpackage",
            name="is_sponsored",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="travelpackage",
            name="sponsorship_amount",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=10),
        ),
        migrations.AddField(
            model_name="travelpackage",
            name="sponsorship_end",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="travelpackage",
            name="sponsorship_priority",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="travelpackage",
            name="sponsorship_start",
            field=models.DateField(blank=True, null=True),
        ),
    ]
