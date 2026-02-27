from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inventory', '0007_invoice_discount_amount_invoice_other_expenses'),
    ]

    operations = [
        migrations.AddField(
            model_name='invoice',
            name='transport_cost',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=12),
        ),
        migrations.AddField(
            model_name='invoice',
            name='labour_cost',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=12),
        ),
    ]

