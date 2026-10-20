# cards/forms.py
from unicodedata import category
from django import forms
from .models import CAT_CHOICES
from .models import Card, DictionaryEntry
from .models import LANG_CHOICES


class CardForm(forms.ModelForm):
    dictionary_entry_id = forms.IntegerField(required=False, widget=forms.HiddenInput)
    question_de = forms.CharField(required=False)

    class Meta:
        model = Card
        fields = ["question_de", "question_en", "answer", "box", "category", "language"]
        labels = {"answer": "Answer / translation"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
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