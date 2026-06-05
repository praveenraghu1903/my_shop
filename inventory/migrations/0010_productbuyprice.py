from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('inventory', '0009_dueinvoice'),
    ]

    operations = [
        migrations.CreateModel(
            name='ProductBuyPrice',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('buy_price', models.DecimalField(decimal_places=2, help_text='Cost price per unit paid to supplier', max_digits=10)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('product', models.OneToOneField(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='buy_price_record',
                    to='inventory.product',
                )),
            ],
        ),
    ]
