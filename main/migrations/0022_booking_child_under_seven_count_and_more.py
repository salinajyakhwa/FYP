from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('main', '0021_travelpackage_max_travelers_bookingcapacityrequest'),
    ]

    operations = [
        migrations.AddField(
            model_name='booking',
            name='child_under_seven_count',
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name='bookingcapacityrequest',
            name='child_under_seven_count',
            field=models.PositiveIntegerField(default=0),
        ),
    ]
