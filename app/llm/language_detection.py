from typing import Optional, List

from lingua import Language, LanguageDetectorBuilder, ConfidenceValue


def detect_language(
    text: str, languages: Optional[List[str]] = None
) -> ConfidenceValue:
    if not languages:
        detector_ = LanguageDetectorBuilder.from_all_languages()
    else:
        detector_ = LanguageDetectorBuilder.from_languages(
            *[Language.from_str(l) for l in languages]
        )
    detector = detector_.build()

    confidences = detector.compute_language_confidence_values(text)
    top = confidences[0]
    return top
