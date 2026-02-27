from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('inventory', '0008_invoice_transport_cost_invoice_labour_cost'),
    ]

    operations = [
        migrations.CreateModel(
            name='DueInvoice',
            fields=[],
            options={
                'verbose_name': 'Due invoice',
                'verbose_name_plural': 'Due invoices',
                'proxy': True,
                'indexes': [],
                'constraints': [],
            },
            bases=('inventory.invoice',),
        ),
    ]

