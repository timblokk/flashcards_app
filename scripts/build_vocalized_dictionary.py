import argparse
import gzip
import json
import struct
import sys
import tarfile
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from cards.arabic import contains_arabic, vocalize_arabic


class PlainTextParser(HTMLParser):
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


def plain_text(markup):
    parser = PlainTextParser()
    parser.feed(markup)
    parser.close()
    return " ".join("".join(parser.parts).split())


def read_member(archive, name):
    member = archive.extractfile(name)
    if member is None:
        raise ValueError(f"Archive is missing {name}")
    return member.read()


def parse_index(index_data, dictionary_data):
    offset = 0
    while offset < len(index_data):
        word_end = index_data.find(b"\0", offset)
        if word_end < 0 or word_end + 9 > len(index_data):
            raise ValueError("Malformed StarDict index record")

        headword = index_data[offset:word_end].decode("utf-8").strip()
        data_offset, data_size = struct.unpack_from(">II", index_data, word_end + 1)
        data_end = data_offset + data_size
        if not headword or data_end > len(dictionary_data):
            raise ValueError(f"Invalid dictionary data offset for {headword!r}")

        markup = dictionary_data[data_offset:data_end].decode("utf-8")
        yield headword, plain_text(markup)
        offset = word_end + 9


def build_dictionary(archive_path, output_path):
    with tarfile.open(archive_path, "r:xz") as archive:
        metadata = read_member(archive, "eng-ara/eng-ara.ifo").decode("utf-8")
        metadata_values = dict(
            line.split("=", 1) for line in metadata.splitlines() if "=" in line
        )
        entry_count = int(metadata_values["wordcount"])
        index_data = gzip.decompress(read_member(archive, "eng-ara/eng-ara.idx.gz"))
        dictionary_data = gzip.decompress(
            read_member(archive, "eng-ara/eng-ara.dict.dz")
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = output_path.with_name(output_path.name + ".tmp")
    processed = 0
    failed_vocalizations = 0

    try:
        with temporary_path.open("w", encoding="utf-8") as output:
            output.write('{"metadata":')
            json.dump({
                "format": "freedict-vocalized-json-v1",
                "language_pair": "en-ar",
                "source": archive_path.name,
                "license": "GPL-2.0-or-later",
                "entry_count": entry_count,
            }, output, ensure_ascii=False)
            output.write(',"entries":[\n')

            for headword, translation in parse_index(index_data, dictionary_data):
                vocalized = vocalize_arabic(translation) if contains_arabic(translation) else ""
                if contains_arabic(translation) and not vocalized:
                    failed_vocalizations += 1

                if processed:
                    output.write(",\n")
                json.dump({
                    "headword": headword,
                    "translation": translation,
                    "vocalized_translation": vocalized,
                }, output, ensure_ascii=False)
                processed += 1

                if processed % 1000 == 0:
                    print(f"Processed {processed}/{entry_count}", file=sys.stderr)

            output.write("\n]}\n")

        if processed != entry_count:
            raise ValueError(f"Expected {entry_count} entries, processed {processed}")
        temporary_path.replace(output_path)
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise

    return processed, failed_vocalizations


def main():
    parser = argparse.ArgumentParser(
        description="Create a JSON dictionary with Mishkal-vocalized Arabic translations."
    )
    parser.add_argument(
        "archive",
        nargs="?",
        type=Path,
        default=ROOT / "freedict-eng-ara-0.6.3.stardict.tar.xz",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "data" / "freedict-eng-ara-0.6.3.vocalized.json",
    )
    args = parser.parse_args()

    if not args.archive.is_file():
        parser.error(f"dictionary archive not found: {args.archive}")

    processed, failed_vocalizations = build_dictionary(args.archive, args.output)
    print(f"Wrote {processed} entries to {args.output}")
    if failed_vocalizations:
        print(f"Entries without a generated vocalization: {failed_vocalizations}")


if __name__ == "__main__":
    main()