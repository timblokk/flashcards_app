import json
from io import StringIO
from tempfile import TemporaryDirectory

from django.core.management import call_command
from django.test import TestCase
from django.template.loader import render_to_string
from django.urls import reverse

from cards.forms import CardForm
from cards.models import Card, DictionaryEntry


class DictionarySuggestionTests(TestCase):
	def setUp(self):
		DictionaryEntry.objects.create(
			language_pair="en-ar",
			headword="Apple",
			translation="التفاحة",
			vocalized_translation="التُّفَّاحَةُ",
		)
		DictionaryEntry.objects.create(
			language_pair="en-ar",
			headword="Application",
			translation="تطبيق",
			vocalized_translation="تَطْبِيقٌ",
		)
		DictionaryEntry.objects.create(
			language_pair="en-ar",
			headword="Water",
			translation="الماء",
			vocalized_translation="الْمَاءُ",
		)

	def test_suggests_prefix_matches_with_translations(self):
		response = self.client.get(reverse("dictionary-suggest"), {"q": "app"})

		self.assertEqual(response.status_code, 200)
		self.assertEqual(
			response.json()["results"],
			[
				{"id": 1, "headword": "Apple", "translation": "التفاحة", "vocalized_translation": "التُّفَّاحَةُ"},
				{"id": 2, "headword": "Application", "translation": "تطبيق", "vocalized_translation": "تَطْبِيقٌ"},
			],
		)

	def test_does_not_search_for_one_character(self):
		response = self.client.get(reverse("dictionary-suggest"), {"q": "a"})

		self.assertEqual(response.json(), {"results": []})

	def test_create_card_accepts_english_arabic_without_german(self):
		response = self.client.post(
			reverse("card-create"),
			{
				"question_de": "",
				"question_en": "Apple",
				"answer": "التفاحة",
				"dictionary_entry_id": DictionaryEntry.objects.get(headword="Apple").id,
				"box": 1,
				"category": "F6",
				"language": "en",
			},
		)

		self.assertRedirects(response, reverse("card-create"))
		card = Card.objects.get(question_en="Apple")
		self.assertEqual(card.answer, "التفاحة")
		self.assertEqual(card.answer_vocalized, "التُّفَّاحَةُ")
		self.assertEqual(card.language, "en")


class ArabicVocalizationTests(TestCase):
	def test_non_arabic_answers_are_not_vocalized(self):
		form = CardForm(data={
			"question_de": "Haus",
			"question_en": "house",
			"answer": "maison",
			"box": 1,
			"category": "F6",
			"language": "de",
		})

		self.assertTrue(form.is_valid())
		card = form.save()

		self.assertEqual(card.answer_vocalized, "")

	def test_card_result_displays_vocalized_answer_right_to_left(self):
		entry = DictionaryEntry.objects.create(
			language_pair="en-ar",
			headword="Apple",
			translation="التفاحة",
			vocalized_translation="التُّفَّاحَةُ",
		)
		form = CardForm(data={
			"question_de": "",
			"question_en": "apple",
			"answer": "التفاحة",
			"dictionary_entry_id": entry.id,
			"box": 1,
			"category": "F6",
			"language": "en",
		})
		self.assertTrue(form.is_valid())
		card = form.save()

		rendered = render_to_string("cards/card.html", {
			"card": card,
			"language": "en",
			"check_card": False,
		})

		self.assertIn("التفاحة", rendered)
		self.assertIn("التُّفَّاحَةُ", rendered)
		self.assertIn('lang="ar" dir="rtl"', rendered)

	def test_import_vocalized_dictionary_stores_both_translations(self):
		payload = {
			"metadata": {
				"format": "freedict-vocalized-json-v1",
				"language_pair": "en-ar",
				"entry_count": 1,
			},
			"entries": [{
				"headword": "Apple",
				"translation": "التفاحة",
				"vocalized_translation": "التُّفَّاحَةُ",
			}],
		}
		with TemporaryDirectory() as directory:
			json_path = f"{directory}/dictionary.json"
			with open(json_path, "w", encoding="utf-8") as dictionary_file:
				json.dump(payload, dictionary_file, ensure_ascii=False)
			call_command("import_vocalized_dictionary", json_path, stdout=StringIO())

		entry = DictionaryEntry.objects.get(language_pair="en-ar", headword="Apple")
		self.assertEqual(entry.translation, "التفاحة")
		self.assertEqual(entry.vocalized_translation, "التُّفَّاحَةُ")
