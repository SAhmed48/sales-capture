# Generated manually for updated_at field

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='submission',
            name='updated_at',
            field=models.DateTimeField(auto_now=True),
        ),
    ]
