import json
from datetime import timedelta
from io import StringIO
from tempfile import TemporaryDirectory

from django.core.management import call_command
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.template.loader import render_to_string
from django.utils import timezone
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
		self.client.force_login(get_user_model().objects.create_user("card-owner"))
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
		self.assertEqual(card.user.username, "card-owner")


class AccountDeckTests(TestCase):
	def create_card(self, **kwargs):
		return Card.objects.create(
			answer="legacy-secret-answer",
			question_en="question",
			question_es="",
			question_de="",
			question_it="",
			question_pt="",
			question_pl="",
			**kwargs,
		)

	def test_card_pages_require_login(self):
		response = self.client.get(reverse("card-list"))

		self.assertRedirects(
			response,
			f"{reverse('login')}?next={reverse('card-list')}",
		)

	def test_card_uniqueness_is_enforced_for_each_language_per_user(self):
		user = get_user_model().objects.create_user("owner")
		other_user = get_user_model().objects.create_user("other")
		question_fields = [
			"question_de",
			"question_en",
			"question_pl",
			"question_it",
			"question_pt",
			"question_es",
		]

		for field in question_fields:
			with self.subTest(language_field=field):
				question_values = {
					question_field: f"{field}-{question_field}"
					for question_field in question_fields
				}
				Card.objects.create(
					user=user,
					answer="translation",
					**question_values,
				)

				duplicate_values = question_values.copy()
				duplicate_values[field] = question_values[field]
				duplicate_values.update({
					question_field: (
						value if question_field == field else f"other-{value}"
					)
					for question_field, value in question_values.items()
				})
				with self.assertRaises(IntegrityError), transaction.atomic():
					Card.objects.create(
						user=user,
						answer="translation",
						**duplicate_values,
					)

				Card.objects.create(
					user=other_user,
					answer="translation",
					**question_values,
				)

	def test_legacy_username_claims_existing_cards_at_signup(self):
		legacy_card = self.create_card()

		response = self.client.post(
			reverse("signup"),
			{
				"username": "legacyUser",
				"password1": "Correct-Horse-92!",
				"password2": "Correct-Horse-92!",
			},
		)

		self.assertRedirects(response, reverse("fiter-categories"))
		user = get_user_model().objects.get(username="legacyUser")
		self.assertTrue(user.check_password("Correct-Horse-92!"))
		legacy_card.refresh_from_db()
		self.assertEqual(legacy_card.user, user)
		self.assertIn("_auth_user_id", self.client.session)

	def test_other_accounts_start_with_empty_private_decks(self):
		legacy_card = self.create_card()
		self.client.post(
			reverse("signup"),
			{
				"username": "legacyUser",
				"password1": "Correct-Horse-92!",
				"password2": "Correct-Horse-92!",
			},
		)
		legacy_user = get_user_model().objects.get(username="legacyUser")

		other_client = self.client_class()
		response = other_client.post(
			reverse("signup"),
			{
				"username": "anotherUser",
				"password1": "A-Different-Password-75!",
				"password2": "A-Different-Password-75!",
			},
		)

		self.assertEqual(response.status_code, 302)
		other_user = get_user_model().objects.get(username="anotherUser")
		self.assertEqual(
			Card.objects.filter(user=other_user).count(),
			0,
		)

		other_client.get(reverse("fiter-categories"))
		response = other_client.get(reverse("card-list"))
		self.assertNotContains(response, "legacy-secret-answer")
		self.assertNotContains(response, "<mark>1</mark>")

		self.client.force_login(legacy_user)
		response = self.client.get(reverse("card-list"))
		self.assertContains(response, "legacy-secret-answer")
		legacy_card.refresh_from_db()
		self.assertEqual(legacy_card.user, legacy_user)

	def test_account_cannot_edit_or_delete_another_users_card(self):
		owner = get_user_model().objects.create_user("owner")
		other_user = get_user_model().objects.create_user("other")
		card = self.create_card(user=owner)
		self.client.force_login(other_user)

		self.assertEqual(
			self.client.get(reverse("card-update", args=[card.pk])).status_code,
			404,
		)
		self.assertEqual(
			self.client.post(reverse("card-delete", args=[card.pk])).status_code,
			404,
		)
		self.assertEqual(
			self.client.post(
				reverse("todo-list"),
				{"card_id": card.pk, "solved": "on"},
			).status_code,
			404,
		)
		self.assertTrue(Card.objects.filter(pk=card.pk).exists())

	def test_box_and_repeat_pages_only_show_the_current_users_cards(self):
		owner = get_user_model().objects.create_user("owner")
		other_user = get_user_model().objects.create_user("other")
		card = self.create_card(user=owner, box=1)
		card.date_moved = timezone.now() - timedelta(days=2)
		card.save(update_fields=["date_moved"])

		self.client.force_login(other_user)
		self.client.get(reverse("fiter-categories"))
		box_response = self.client.get(reverse("box", args=[1]))
		repeat_response = self.client.get(reverse("todo-list"))

		self.assertNotContains(box_response, "legacy-secret-answer")
		self.assertContains(box_response, "<mark>0</mark>")
		self.assertNotContains(repeat_response, "legacy-secret-answer")
		self.assertContains(repeat_response, "<mark>0</mark>")

		self.client.force_login(owner)
		self.client.get(reverse("fiter-categories"))
		self.assertContains(self.client.get(reverse("box", args=[1])), "legacy-secret-answer")
		self.assertContains(self.client.get(reverse("todo-list")), "legacy-secret-answer")


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
