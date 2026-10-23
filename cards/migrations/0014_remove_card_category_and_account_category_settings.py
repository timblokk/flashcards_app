from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("cards", "0013_consolidate_question_field"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="card",
            name="category",
        ),
        migrations.DeleteModel(
            name="AccountCategorySettings",
        ),
    ]
