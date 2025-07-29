from typing import Optional, List

from lingua import Language, LanguageDetectorBuilder


async def detect_language(
    text: str, languages: Optional[List[str]] = None
) -> Optional[str]:
    if not languages:
        detector_ = LanguageDetectorBuilder.from_all_languages()
    else:
        detector_ = LanguageDetectorBuilder.from_languages(
            *[Language.from_str(l) for l in languages]
        )
    detector = detector_.build()

    # confidence = detector.compute_language_confidence_values(text)
    if language := detector.detect_language_of(text):
        return language.name
