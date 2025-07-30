from babel import Locale
from flag import flag

from core.auth import User

from ..notes import get_language
from .. import Config


def get_native_language(user: User):
    default = Config.LANGUAGE["defaults"]["native"]
    return get_language(user.get_option("native_language", default))


def get_studied_language(user: User):
    default = Config.LANGUAGE["defaults"]["study"]
    return get_language(user.get_option("studied_language", default))


def get_flag(locale: Locale) -> str:
    if terr := Config.LANGUAGE["territories"].get(locale.language):
        return flag(terr)
    return ""
