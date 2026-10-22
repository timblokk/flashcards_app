from django.test import TestCase
from django.urls import reverse

from cards.models import Card, DictionaryEntry


class DictionarySuggestionTests(TestCase):
	def setUp(self):
		DictionaryEntry.objects.create(
			language_pair="en-ar",
			headword="Apple",
			translation="التفاحة",
		)
		DictionaryEntry.objects.create(
			language_pair="en-ar",
			headword="Application",
			translation="تطبيق",
		)
		DictionaryEntry.objects.create(
			language_pair="en-ar",
			headword="Water",
			translation="الماء",
		)

	def test_suggests_prefix_matches_with_translations(self):
		response = self.client.get(reverse("dictionary-suggest"), {"q": "app"})

		self.assertEqual(response.status_code, 200)
		self.assertEqual(
			response.json()["results"],
			[
				{"headword": "Apple", "translation": "التفاحة"},
				{"headword": "Application", "translation": "تطبيق"},
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
				"box": 1,
				"category": "F6",
				"language": "en",
			},
		)

		self.assertRedirects(response, reverse("card-create"))
		card = Card.objects.get(question_en="Apple")
		self.assertEqual(card.answer, "التفاحة")
		self.assertEqual(card.language, "en")
