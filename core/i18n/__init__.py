# The concept is this:
#
# - a delayed string class gets and stores English strings
# - there is a function which collects all the declared entities of this class and saves them in a `.pot` file;
# - There is a function to resolve the delayed string, which takes it and the locale and returns the string in a given language.
# - Language files are stored in `data/locale/` folder in gettext `.po` format.
# - The resolving function implements lazy-loading of language files: a language file is loaded when the user with this language makes a request.
# - There is support for translating on demand: if a user with a new language appears, the background translation is started via some external api (e.g. Google Translate or an OpenAI-compatible LLM) and, when finished, is saved into a new language file.
# - If a delayed string is not resolved till the time of usage, it defaults to its English value.
# - Delayed strings behave like regulr strings as much as possible, e.g. they're serializable.
# - This mechanics tries to be compliant with gettext logic and file format, but allows fine control of strings resolution and simplifies generating new translations.
# - If an application is started without any `.po` files, it generates them on the fly not bothering the user, and generates translation files on demand, allowing to improve the translation later.
#
# Example workflow:
# 1.  *Developer*: Adds `NEW_FEATURE_PROMPT = TranslatableString("Please enable the new feature.")` to `app/features/new.py`.
# 2.  *Developer*: Runs `python scripts/collect_strings.py`. The `messages.pot` file is updated with the new string.
# 3.  *User A (locale: `es`)*: Interacts with the bot. The feature prompt needs to be displayed.
# 4.  *System*: `ctx.resolve(NEW_FEATURE_PROMPT)` is called.
# 5.  *System*: `Context` checks for `data/locale/es/LC_MESSAGES/messages.mo`. It doesn't exist.
# 6.  *System*: A background task is launched to translate all strings in `messages.pot` to Spanish and create `messages.po`/`.mo`.
# 7.  *System*: For the current request, `resolve` falls back and returns the English string: "Please enable the new feature.".
# 8.  *User B (locale: `es`)*: Later makes a request that also requires the same prompt.
# 9.  *System*: By now, the background task has finished, and `messages.mo` exists.
# 10. *System*: `Context` lazy-loads `data/locale/es/LC_MESSAGES/messages.mo` into its cache.
# 11. *System*: `resolve` now looks up the string and returns the Spanish version: "Por favor, active la nueva función.".


import logging

import os
from typing import Callable, Coroutine, Dict, Optional, Set

import polib

logger = logging.getLogger(__name__)


class TranslatableString:
    """
    Represents a string that can be translated. Instances are registered
    globally to be collected into a .pot file.
    """

    _registry: Set["TranslatableString"] = set()

    def __init__(self, msgid: str, comment: Optional[str] = None):
        if not isinstance(msgid, str) or not msgid:
            raise ValueError("msgid must be a non-empty string.")
        self.msgid = msgid
        self.comment = comment
        self._registry.add(self)

    def __str__(self) -> str:
        # Default to the English msgid if not resolved.
        return self.msgid

    def __repr__(self) -> str:
        return f"TranslatableString('{self.msgid}')"

    def __hash__(self):
        return hash(self.msgid)

    def __eq__(self, other):
        return (
            isinstance(other, TranslatableString) and self.msgid == other.msgid
        )


_translation_cache: Dict[str, Optional[polib.POFile]] = {}

# The flow:
# no file -> no entry -> entry without translation -> entry with translation


def create_locale_file(locale: str):
    """
    Create a .po file with all the strings found in the app.
    Leave translations empty.
    """
    # This is a placeholder for the script that would generate the .pot file
    # and then create specific .po files from it.
    # For the purpose of this example, we assume this is handled by a
    # separate script like `scripts/collect_strings.py`.
    pass


def resolve(string: TranslatableString, locale: str) -> str:
    """
    Get the translation from data/locale/*.po file or return the English default.
    Implements lazy-loading and caching of translation files.
    """
    logger.info(f"Got translation request for the locale: {locale}")
    if not isinstance(string, TranslatableString):
        raise TypeError("resolve() expects a TranslatableString instance.")
    if not locale:
        return string.msgid

    translations = _translation_cache.get(locale)
    if translations is None and locale not in _translation_cache:
        # Not in cache, attempt to load
        po_path = os.path.join(
            "data", "locale", locale, "LC_MESSAGES", "messages.po"
        )
        mo_path = os.path.join(
            "data", "locale", locale, "LC_MESSAGES", "messages.mo"
        )

        try:
            # Production environments should prefer compiled .mo files for performance
            if os.path.exists(mo_path):
                translations = polib.mofile(mo_path)
                logger.info(f"Loaded .mo file for locale '{locale}'")
            elif os.path.exists(po_path):
                translations = polib.pofile(po_path)
                logger.info(f"Loaded .po file for locale '{locale}'")
            else:
                logger.warning(
                    f"No .po or .mo file found for locale '{locale}'."
                )
                # In a real app, this is where you might trigger a
                # background task to generate the translation file.
                translations = None
        except Exception as e:
            logger.error(
                f"Failed to load translation file for locale '{locale}': {e}"
            )
            translations = None

        _translation_cache[locale] = translations

    if translations:
        entry = translations.find(string.msgid)
        if entry and entry.msgstr:
            return entry.msgstr

    # Fallback to the original msgid
    return string.msgid
