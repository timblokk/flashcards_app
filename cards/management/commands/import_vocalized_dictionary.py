import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from cards.models import DictionaryEntry


class Command(BaseCommand):
    help = "Import a pre-vocalized JSON dictionary without requiring Mishkal."

    def add_arguments(self, parser):
        parser.add_argument("json_file", type=Path)

    def handle(self, *args, **options):
        path = options["json_file"]
        if not path.is_file():
            raise CommandError(f"Dictionary JSON file not found: {path}")

        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise CommandError(f"Could not read dictionary JSON: {error}") from error

        metadata = payload.get("metadata") if isinstance(payload, dict) else None
        entries = payload.get("entries") if isinstance(payload, dict) else None
        if not isinstance(metadata, dict) or not isinstance(entries, list):
            raise CommandError("Dictionary JSON must contain metadata and entries")
        if metadata.get("format") != "freedict-vocalized-json-v1":
            raise CommandError("Unsupported or missing vocalized dictionary format")

        language_pair = metadata.get("language_pair")
        expected_count = metadata.get("entry_count")
        if (
            not isinstance(language_pair, str)
            or not isinstance(expected_count, int)
            or len(entries) != expected_count
        ):
            raise CommandError("Dictionary metadata does not match the entries")

        batch = []
        with transaction.atomic():
            DictionaryEntry.objects.filter(language_pair=language_pair).delete()
            for position, item in enumerate(entries, start=1):
                if not isinstance(item, dict):
                    raise CommandError(f"Entry {position} is not an object")

                headword = item.get("headword")
                translation = item.get("translation")
                vocalized_translation = item.get("vocalized_translation", "")
                if not all(
                    isinstance(value, str)
                    for value in (headword, translation, vocalized_translation)
                ):
                    raise CommandError(f"Entry {position} has invalid text fields")

                batch.append(DictionaryEntry(
                    language_pair=language_pair,
                    headword=headword,
                    search_key=headword.casefold(),
                    translation=translation,
                    vocalized_translation=vocalized_translation,
                ))
                if len(batch) == 1000:
                    DictionaryEntry.objects.bulk_create(batch, batch_size=1000)
                    batch.clear()

            if batch:
                DictionaryEntry.objects.bulk_create(batch, batch_size=1000)

        self.stdout.write(self.style.SUCCESS(f"Imported {expected_count} {language_pair} entries."))