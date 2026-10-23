from django.db import migrations, models


QUESTION_FIELDS = {
    "de": "question_de",
    "en": "question_en",
    "pl": "question_pl",
    "it": "question_it",
    "pt": "question_pt",
    "es": "question_es",
}


def consolidate_questions(apps, schema_editor):
    Card = apps.get_model("cards", "Card")
    database = schema_editor.connection.alias
    fallback_fields = tuple(QUESTION_FIELDS.values())

    used_questions = {}
    cards = []
    for card in Card.objects.using(database).order_by("pk").iterator():
        preferred_field = QUESTION_FIELDS.get(card.language)
        question = getattr(card, preferred_field, "") if preferred_field else ""
        if not question:
            question = next(
                (
                    getattr(card, field)
                    for field in fallback_fields
                    if getattr(card, field)
                ),
                "",
            )
        if question and card.user_id is not None:
            used_for_user = used_questions.setdefault(card.user_id, set())
            base_question = question
            suffix_number = 2
            while question in used_for_user:
                suffix = f" ({suffix_number})"
                question = f"{base_question[:100 - len(suffix)]}{suffix}"
                suffix_number += 1
            used_for_user.add(question)
        card.question = question
        cards.append(card)
        if len(cards) == 500:
            Card.objects.using(database).bulk_update(cards, ["question"])
            cards.clear()
    if cards:
        Card.objects.using(database).bulk_update(cards, ["question"])


def restore_questions(apps, schema_editor):
    Card = apps.get_model("cards", "Card")
    database = schema_editor.connection.alias

    used_fields = {}
    cards = []
    for card in Card.objects.using(database).all().iterator():
        if card.question:
            pair = (
                (card.user_id, card.answer, card.question)
                if card.user_id is not None
                else (card.pk, card.answer, card.question)
            )
            used_for_pair = used_fields.setdefault(pair, set())
            language_code, question_field = next(
                (
                    (code, field)
                    for code, field in QUESTION_FIELDS.items()
                    if code not in used_for_pair
                ),
                (None, None),
            )
            if question_field is None:
                raise RuntimeError(
                    "Cannot reverse the question migration: more than six "
                    "identical question and answer cards exist for one user."
                )
            setattr(card, question_field, card.question)
            card.language = language_code
            used_for_pair.add(language_code)
            cards.append(card)
        if len(cards) == 500:
            Card.objects.using(database).bulk_update(
                cards,
                [*QUESTION_FIELDS.values(), "language"],
            )
            cards.clear()
    if cards:
        Card.objects.using(database).bulk_update(
            cards,
            [*QUESTION_FIELDS.values(), "language"],
        )


class Migration(migrations.Migration):

    dependencies = [
        ("cards", "0012_remove_card_uniq_card_user_answer_de_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="card",
            name="question",
            field=models.CharField(default="", max_length=100),
            preserve_default=False,
        ),
        migrations.RunPython(
            consolidate_questions,
            restore_questions,
        ),
        migrations.RemoveConstraint(
            model_name="card",
            name="uniq_card_user_answer_de",
        ),
        migrations.RemoveConstraint(
            model_name="card",
            name="uniq_card_user_answer_en",
        ),
        migrations.RemoveConstraint(
            model_name="card",
            name="uniq_card_user_answer_pl",
        ),
        migrations.RemoveConstraint(
            model_name="card",
            name="uniq_card_user_answer_it",
        ),
        migrations.RemoveConstraint(
            model_name="card",
            name="uniq_card_user_answer_pt",
        ),
        migrations.RemoveConstraint(
            model_name="card",
            name="uniq_card_user_answer_es",
        ),
        migrations.AlterField(
            model_name="card",
            name="question_de",
            field=models.CharField(default="", max_length=100),
        ),
        migrations.AlterField(
            model_name="card",
            name="question_en",
            field=models.CharField(default="", max_length=100),
        ),
        migrations.AlterField(
            model_name="card",
            name="question_pl",
            field=models.CharField(default="", max_length=100),
        ),
        migrations.AlterField(
            model_name="card",
            name="question_it",
            field=models.CharField(default="", max_length=100),
        ),
        migrations.AlterField(
            model_name="card",
            name="question_pt",
            field=models.CharField(default="", max_length=100),
        ),
        migrations.AlterField(
            model_name="card",
            name="question_es",
            field=models.CharField(default="", max_length=100),
        ),
        migrations.RemoveField(
            model_name="card",
            name="question_de",
        ),
        migrations.RemoveField(
            model_name="card",
            name="question_en",
        ),
        migrations.RemoveField(
            model_name="card",
            name="question_pl",
        ),
        migrations.RemoveField(
            model_name="card",
            name="question_it",
        ),
        migrations.RemoveField(
            model_name="card",
            name="question_pt",
        ),
        migrations.RemoveField(
            model_name="card",
            name="question_es",
        ),
        migrations.RemoveField(
            model_name="card",
            name="language",
        ),
        migrations.AddConstraint(
            model_name="card",
            constraint=models.UniqueConstraint(
                condition=~models.Q(question=""),
                fields=("user", "question"),
                name="uniq_card_user_question",
            ),
        ),
    ]
