from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("money_app", "0007_alter_expense_date"),
    ]

    operations = [
        migrations.CreateModel(
            name="Tag",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=100)),
                ("normalized_name", models.CharField(editable=False, max_length=100)),
                ("owner", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="tags", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "ordering": ["name"],
                "constraints": [
                    models.UniqueConstraint(fields=("owner", "normalized_name"), name="money_app_tag_owner_normalized_name_unique"),
                ],
            },
        ),
        migrations.AddField(
            model_name="expense",
            name="tags",
            field=models.ManyToManyField(blank=True, related_name="expenses", to="money_app.tag"),
        ),
    ]
