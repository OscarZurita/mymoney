import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("money_app", "0004_alter_expense_description"),
    ]

    operations = [
        migrations.AlterField(
            model_name="expense",
            name="category",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="expenses",
                to="money_app.category",
            ),
        ),
        migrations.AlterField(
            model_name="expense",
            name="date",
            field=models.DateTimeField(
                blank=True,
                default=django.utils.timezone.now,
                verbose_name="Date spent",
            ),
        ),
    ]
