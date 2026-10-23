import logging
import re
from functools import lru_cache
from threading import Lock


logger = logging.getLogger(__name__)
_VOCALIZER_LOCK = Lock()
_ARABIC_CHARACTERS = re.compile(r"[\u0600-\u06ff\u0750-\u077f\u08a0-\u08ff]")


def contains_arabic(text):
    return bool(_ARABIC_CHARACTERS.search(text or ""))


@lru_cache(maxsize=1)
def _get_vocalizer():
    from mishkal.tashkeel import TashkeelClass

    return TashkeelClass()


@lru_cache(maxsize=2048)
def vocalize_arabic(text):
    if not contains_arabic(text):
        return ""

    try:
        with _VOCALIZER_LOCK:
            return _get_vocalizer().tashkeel(text).strip()
    except Exception:
        logger.exception("Mishkal could not vocalize an Arabic answer")
        return ""