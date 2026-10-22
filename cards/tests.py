import json
from io import BytesIO
from datetime import timedelta
from io import StringIO
from tempfile import TemporaryDirectory

from django.core.management import call_command
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.core.files.uploadedfile import SimpleUploadedFile
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
				"category": "Arabic",
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

	def test_new_account_only_sees_and_can_select_arabic_category(self):
		self.client.post(
			reverse("signup"),
			{
				"username": "new-user",
				"password1": "Correct-Horse-92!",
				"password2": "Correct-Horse-92!",
			},
		)
		user = get_user_model().objects.get(username="new-user")

		filter_response = self.client.get(
			reverse("fiter-categories"),
			{"category": "F6", "language": "de"},
		)
		self.assertContains(filter_response, 'value="Arabic"')
		self.assertNotContains(filter_response, '<option value="F6">')
		self.assertNotContains(filter_response, '<option value="livres">')
		self.assertEqual(self.client.session["category"], "Arabic")

		create_response = self.client.get(reverse("card-create"))
		self.assertContains(create_response, 'value="Arabic"')
		self.assertNotContains(create_response, '<option value="F6">')

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
		self.assertEqual(response.status_code, 200)
		self.assertFalse(Card.objects.filter(user=user).exists())

		response = self.client.post(
			reverse("card-create"),
			{
				"question_de": "",
				"question_en": "Apple",
				"answer": "التفاحة",
				"box": 1,
				"category": "Arabic",
				"language": "en",
			},
		)
		self.assertRedirects(response, reverse("card-create"))
		self.assertEqual(Card.objects.get(user=user).category, "Arabic")

	def test_signup_shows_password_validation_errors(self):
		response = self.client.get(reverse("signup"))

		self.assertContains(response, "Password requirements")
		self.assertContains(response, "at least 8 characters")
		self.assertContains(response, "commonly used password")
		self.assertContains(response, "entirely numeric")
		self.assertContains(response, "too similar to your other personal information")

		response = self.client.post(
			reverse("signup"),
			{
				"username": "new-user",
				"password1": "short",
				"password2": "short",
			},
		)

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, "This password is too short")
		self.assertContains(response, 'role="alert"')
		self.assertFalse(
			get_user_model().objects.filter(username="new-user").exists()
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
		card = self.create_card(user=owner, box=1, category="Arabic")
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


class CardImportTests(TestCase):
	def setUp(self):
		self.user = get_user_model().objects.create_user("importer")
		self.client.force_login(self.user)

	def upload(self, filename, content, language="en"):
		return self.client.post(
			reverse("card-import"),
			{
				"file": SimpleUploadedFile(filename, content),
				"language": language,
			},
		)

	def test_csv_upload_creates_owned_arabic_cards_in_selected_language(self):
		DictionaryEntry.objects.create(
			language_pair="en-ar",
			headword="hello",
			translation="مرحبا",
			vocalized_translation="مَرْحَبًا",
		)
		response = self.upload(
			"cards.csv",
			b"question,answer\nhello,\xd9\x85\xd8\xb1\xd8\xad\xd8\xa8\xd8\xa7\nbye,goodbye\n",
			language="en",
		)

		self.assertRedirects(response, reverse("card-list"))
		self.assertEqual(list(response.wsgi_request._messages)[0].message, "Imported 2 cards.")
		cards = list(Card.objects.filter(user=self.user).order_by("id"))
		self.assertEqual(len(cards), 2)
		self.assertEqual(cards[0].question_en, "hello")
		self.assertEqual(cards[0].answer, "مرحبا")
		self.assertEqual(cards[0].answer_vocalized, "مَرْحَبًا")
		self.assertEqual(cards[0].category, "Arabic")
		self.assertEqual(cards[0].language, "en")
		self.assertEqual(cards[0].box, 1)
		self.assertEqual(cards[0].question_de, "")
		self.assertEqual(cards[1].answer_vocalized, "")
		other_user = get_user_model().objects.create_user("other-deck")
		self.assertEqual(Card.objects.filter(user=other_user).count(), 0)

	def test_xlsx_upload_creates_cards_in_selected_language(self):
		from openpyxl import Workbook

		workbook = Workbook()
		worksheet = workbook.active
		worksheet.append(["question", "answer"])
		worksheet.append(["Haus", "house"])
		content = BytesIO()
		workbook.save(content)

		response = self.upload("cards.xlsx", content.getvalue(), language="de")

		self.assertRedirects(response, reverse("card-list"))
		card = Card.objects.get(user=self.user)
		self.assertEqual(card.question_de, "Haus")
		self.assertEqual(card.answer, "house")
		self.assertEqual(card.language, "de")

	def test_duplicate_rows_are_skipped_and_reported_after_import(self):
		response = self.upload(
			"cards.csv",
			b"question,answer\nhello,world\nhello,world\nbye,goodbye\n",
		)

		self.assertRedirects(response, reverse("card-list"))
		self.assertEqual(Card.objects.filter(user=self.user).count(), 2)
		message = list(response.wsgi_request._messages)[0]
		self.assertEqual(
			message.message,
			"Imported 2 cards. Skipped 1 duplicate card: hello.",
		)
		self.assertTrue(message.tags.startswith("warning"))

	def test_invalid_csv_imports_nothing(self):
		response = self.upload("bad.csv", b"front,back\nhello,world\n")
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, "exactly two columns")
		self.assertEqual(Card.objects.filter(user=self.user).count(), 0)

		response = self.upload(
			"invalid-row.csv",
			b"question,answer\nvalid question,valid answer\n,missing question\n",
		)
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, "Row 3")
		self.assertEqual(Card.objects.filter(user=self.user).count(), 0)

	def test_upload_skips_existing_duplicate_but_imports_other_rows(self):
		Card.objects.create(
			user=self.user,
			answer="world",
			question_en="hello",
			question_es="",
			question_de="",
			question_it="",
			question_pt="",
			question_pl="",
			category="Arabic",
			language="en",
		)
		other_user = get_user_model().objects.create_user("other-importer")
		Card.objects.create(
			user=other_user,
			answer="world",
			question_en="other question",
			question_es="",
			question_de="",
			question_it="",
			question_pt="",
			question_pl="",
			category="Arabic",
			language="en",
		)

		response = self.upload(
			"cards.csv",
			b"question,answer\nhello,world\nnew question,new answer\n",
		)

		self.assertRedirects(response, reverse("card-list"))
		self.assertEqual(Card.objects.filter(user=self.user).count(), 2)
		self.assertEqual(Card.objects.filter(user=other_user).count(), 1)
		message = list(response.wsgi_request._messages)[0]
		self.assertEqual(
			message.message,
			"Imported 1 card. Skipped 1 duplicate card: hello.",
		)

	def test_upload_requires_login(self):
		self.client.logout()
		response = self.upload("cards.csv", b"question,answer\nhello,world\n")

		self.assertEqual(response.status_code, 302)
		self.assertIn(reverse("login"), response.url)


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
