import gzip
import html
import struct
import tarfile
from html.parser import HTMLParser
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from cards.models import DictionaryEntry


class _PlainTextParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag in {"br", "div", "li", "p"}:
            self.parts.append(" ")

    def handle_endtag(self, tag):
        if tag in {"div", "li", "p"}:
            self.parts.append(" ")

    def handle_data(self, data):
        self.parts.append(data)


def _plain_text(markup):
    parser = _PlainTextParser()
    parser.feed(markup)
    parser.close()
    return " ".join("".join(parser.parts).split())


def _read_member(archive, name):
    try:
        member = archive.extractfile(name)
    except KeyError as error:
        raise CommandError(f"StarDict archive is missing {name}") from error
    if member is None:
        raise CommandError(f"Unable to read {name} from StarDict archive")
    return member.read()


def _parse_entries(index_data, dictionary_data, language_pair):
    offset = 0
    entries = []
    while offset < len(index_data):
        word_end = index_data.find(b"\0", offset)
        if word_end < 0 or word_end + 9 > len(index_data):
            raise CommandError("Malformed StarDict index record")

        try:
            headword = index_data[offset:word_end].decode("utf-8").strip()
            data_offset, data_size = struct.unpack_from(">II", index_data, word_end + 1)
            markup = dictionary_data[data_offset:data_offset + data_size].decode("utf-8")
        except (UnicodeDecodeError, struct.error) as error:
            raise CommandError("Invalid UTF-8 or offsets in StarDict data") from error

        if not headword or data_offset + data_size > len(dictionary_data):
            raise CommandError("StarDict index points outside its dictionary data")

        entries.append(DictionaryEntry(
            language_pair=language_pair,
            headword=headword,
            search_key=headword.casefold(),
            translation=_plain_text(markup),
        ))
        offset = word_end + 9

    return entries


class Command(BaseCommand):
    help = "Import a StarDict .tar.xz dictionary into the local searchable dictionary."

    def add_arguments(self, parser):
        parser.add_argument("archive", type=Path)
        parser.add_argument("--language-pair", default="en-ar")

    def handle(self, *args, **options):
        archive_path = options["archive"]
        if not archive_path.is_file():
            raise CommandError(f"Dictionary archive not found: {archive_path}")

        try:
            with tarfile.open(archive_path, "r:xz") as archive:
                metadata = _read_member(archive, "eng-ara/eng-ara.ifo").decode("utf-8")
                index_data = gzip.decompress(_read_member(archive, "eng-ara/eng-ara.idx.gz"))
                dictionary_data = gzip.decompress(_read_member(archive, "eng-ara/eng-ara.dict.dz"))
        except (OSError, tarfile.TarError, UnicodeDecodeError, gzip.BadGzipFile) as error:
            raise CommandError(f"Could not read StarDict archive: {error}") from error

        metadata_values = dict(
            line.split("=", 1)
            for line in metadata.splitlines()
            if "=" in line
        )
        try:
            expected_count = int(metadata_values["wordcount"])
        except (KeyError, ValueError) as error:
            raise CommandError("StarDict metadata has no valid wordcount") from error

        entries = _parse_entries(index_data, dictionary_data, options["language_pair"])
        if len(entries) != expected_count:
            raise CommandError(
                f"Expected {expected_count} entries from metadata, parsed {len(entries)}"
            )

        with transaction.atomic():
            DictionaryEntry.objects.filter(language_pair=options["language_pair"]).delete()
            DictionaryEntry.objects.bulk_create(entries, batch_size=500)

        self.stdout.write(self.style.SUCCESS(f"Imported {len(entries)} {options['language_pair']} entries."))