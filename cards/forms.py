# cards/forms.py
from unicodedata import category
from django import forms
from django.core.exceptions import ValidationError
from django.db.models import Q
from .models import CAT_CHOICES
from .models import BOXES, Card, DictionaryEntry
from .models import LANG_CHOICES
from .card_import import parse_card_import


QUESTION_FIELDS = {
    "de": "question_de",
    "en": "question_en",
    "pl": "question_pl",
    "it": "question_it",
    "pt": "question_pt",
    "es": "question_es",
}


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
    question_de = forms.CharField(required=False)

    class Meta:
        model = Card
        fields = ["question_de", "question_en", "answer", "box", "category", "language"]
        labels = {"answer": "Answer / translation"}

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if user is not None:
            self.fields["category"].choices = get_category_choices(user)
            self.fields["category"].initial = get_default_category(user)
        self._original_answer = self.instance.answer
        self._original_language = self.instance.language
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
                cleaned_data["question_en"] = self._dictionary_entry.headword
                cleaned_data["answer"] = self._dictionary_entry.translation
                cleaned_data["language"] = "en"
        return cleaned_data

    def save(self, commit=True):
        card = super().save(commit=False)
        if self._dictionary_entry:
            card.answer_vocalized = self._dictionary_entry.vocalized_translation
        elif (
            card.answer != self._original_answer
            or card.language != self._original_language
        ):
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
    category= forms.ChoiceField(choices= CAT_CHOICES)
    language= forms.ChoiceField(choices= LANG_CHOICES)

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if user is not None:
            self.fields["category"].choices = get_category_choices(user)
            self.fields["category"].initial = get_default_category(user)


class CardImportForm(forms.Form):
    file = forms.FileField(label="CSV or Excel file")
    language = forms.ChoiceField(
        choices=LANG_CHOICES,
        required=False,
        label="Question language (for two-column files)",
        help_text="Three-column export files include a language per card.",
    )

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user

    def clean(self):
        cleaned_data = super().clean()
        uploaded_file = cleaned_data.get("file")
        language = cleaned_data.get("language")
        if uploaded_file is None:
            return cleaned_data

        try:
            rows = parse_card_import(uploaded_file)
        except ValidationError as error:
            self.add_error("file", error)
            return cleaned_data

        allowed_languages = {value for value, _ in LANG_CHOICES}
        rows_with_language = []
        invalid_language_rows = []
        for row_number, question, answer, file_language in rows:
            row_language = file_language or language
            if row_language not in allowed_languages:
                invalid_language_rows.append(row_number)
                continue
            rows_with_language.append((
                row_number,
                question,
                answer,
                row_language,
                QUESTION_FIELDS[row_language],
            ))
        if invalid_language_rows:
            row_list = ", ".join(str(row) for row in invalid_language_rows[:20])
            if len(invalid_language_rows) > 20:
                row_list += ", ..."
            self.add_error(
                "file",
                f"Choose a question language for two-column files or provide a "
                f"valid language in row(s): {row_list}.",
            )
            return cleaned_data

        max_answer_length = Card._meta.get_field("answer").max_length
        oversized_rows = [
            row_number
            for row_number, question, answer, _, question_field in rows_with_language
            if (
                len(question) > Card._meta.get_field(question_field).max_length
                or len(answer) > max_answer_length
            )
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

        existing_pairs = set()
        for language_code, question_field in QUESTION_FIELDS.items():
            language_pairs = [
                (answer, question)
                for _, question, answer, row_language, _ in rows_with_language
                if row_language == language_code
            ]
            for offset in range(0, len(language_pairs), 100):
                pair_batch = language_pairs[offset:offset + 100]
                query = Q()
                for answer, question in pair_batch:
                    query |= Q(answer=answer, **{question_field: question})
                existing_pairs.update(
                    (language_code, answer, question)
                    for answer, question in Card.objects.filter(user=self.user)
                    .filter(query)
                    .values_list("answer", question_field)
                )

        import_rows = []
        duplicate_questions = []
        duplicate_count = 0
        seen_pairs = set()
        for row_number, question, answer, row_language, question_field in rows_with_language:
            pair = (row_language, answer, question)
            if pair in seen_pairs or pair in existing_pairs:
                duplicate_count += 1
                if question not in duplicate_questions:
                    duplicate_questions.append(question)
                continue
            seen_pairs.add(pair)
            import_rows.append((
                row_number,
                question,
                answer,
                row_language,
                question_field,
            ))

        cleaned_data["rows"] = import_rows
        cleaned_data["duplicate_count"] = duplicate_count
        cleaned_data["duplicate_questions"] = duplicate_questions
        return cleaned_data