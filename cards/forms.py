# cards/forms.py
from unicodedata import category
from django import forms
from django.core.exceptions import ValidationError
from django.db.models import Q
from .models import CAT_CHOICES
from .models import BOXES, Card, DictionaryEntry
from .card_import import parse_card_import


def get_category_choices(user):
    category_settings = getattr(user, "category_settings", None)
    if category_settings is None or category_settings.arabic_only:
        return [("Arabic", "Arabic")]
    return CAT_CHOICES


def get_default_category(user):
    category_settings = getattr(user, "category_settings", None)
    if category_settings is not None and not category_settings.arabic_only:
        return "F6"
    return "Arabic"


class CardForm(forms.ModelForm):
    dictionary_entry_id = forms.IntegerField(required=False, widget=forms.HiddenInput)

    class Meta:
        model = Card
        fields = ["question", "answer", "box", "category"]
        labels = {"answer": "Answer / translation"}

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user or self.instance.user
        if user is not None:
            self.fields["category"].choices = get_category_choices(user)
            self.fields["category"].initial = get_default_category(user)
        self._original_answer = self.instance.answer
        self._original_vocalized_answer = self.instance.answer_vocalized
        self._dictionary_entry = None

    def clean(self):
        cleaned_data = super().clean()
        entry_id = cleaned_data.get("dictionary_entry_id")
        if entry_id:
            self._dictionary_entry = DictionaryEntry.objects.filter(
                pk=entry_id,
                language_pair="en-ar",
            ).first()
            if self._dictionary_entry is None:
                self.add_error("dictionary_entry_id", "Choose a valid dictionary suggestion.")
            else:
                cleaned_data["question"] = self._dictionary_entry.headword
                cleaned_data["answer"] = self._dictionary_entry.translation
        question = cleaned_data.get("question")
        answer = cleaned_data.get("answer")
        if question and self.user is not None:
            duplicates = Card.objects.filter(
                user=self.user,
                question=question,
            )
            if self.instance.pk:
                duplicates = duplicates.exclude(pk=self.instance.pk)
            if duplicates.exists():
                self.add_error(
                    "question",
                    "A card with this question already exists.",
                )
        return cleaned_data

    def save(self, commit=True):
        card = super().save(commit=False)
        if self._dictionary_entry:
            card.answer_vocalized = self._dictionary_entry.vocalized_translation
        elif card.answer != self._original_answer:
            card.answer_vocalized = ""
        else:
            card.answer_vocalized = self._original_vocalized_answer

        if commit:
            card.save()
            self.save_m2m()
        return card


class CardCheckForm(forms.Form):
    card_id = forms.IntegerField(required=True)
    solved = forms.BooleanField(required=False)

class CardUpdateForm(forms.Form):
    card_id = forms.IntegerField(required=True)
    solved = forms.BooleanField(required=False)

class CardCategoriesFilterForm(forms.Form):
    category = forms.ChoiceField(choices=CAT_CHOICES)

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if user is not None:
            self.fields["category"].choices = get_category_choices(user)
            self.fields["category"].initial = get_default_category(user)


class CardImportForm(forms.Form):
    file = forms.FileField(label="CSV or Excel file")

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user

    def clean(self):
        cleaned_data = super().clean()
        uploaded_file = cleaned_data.get("file")
        if uploaded_file is None:
            return cleaned_data

        try:
            rows = parse_card_import(uploaded_file)
        except ValidationError as error:
            self.add_error("file", error)
            return cleaned_data

        max_answer_length = Card._meta.get_field("answer").max_length
        oversized_rows = [
            row_number for row_number, question, answer in rows
            if len(question) > Card._meta.get_field("question").max_length
            or len(answer) > max_answer_length
        ]
        if oversized_rows:
            row_list = ", ".join(str(row) for row in oversized_rows[:20])
            if len(oversized_rows) > 20:
                row_list += ", ..."
            self.add_error(
                "file",
                f"Text exceeds the card field length in row(s): {row_list}. "
                "No cards were imported.",
            )
            return cleaned_data

        questions = [question for _, question, _ in rows]
        existing_questions = set()
        for offset in range(0, len(questions), 500):
            query = Q()
            for question in questions[offset:offset + 500]:
                query |= Q(question=question)
            existing_questions.update(
                Card.objects.filter(user=self.user)
                .filter(query)
                .values_list("question", flat=True)
            )

        import_rows = []
        duplicate_questions = []
        duplicate_count = 0
        seen_questions = set()
        for row_number, question, answer in rows:
            if question in seen_questions or question in existing_questions:
                duplicate_count += 1
                if question not in duplicate_questions:
                    duplicate_questions.append(question)
                continue
            seen_questions.add(question)
            import_rows.append((row_number, question, answer))

        cleaned_data["rows"] = import_rows
        cleaned_data["duplicate_count"] = duplicate_count
        cleaned_data["duplicate_questions"] = duplicate_questions
        return cleaned_data