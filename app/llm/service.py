import logging
from typing import Optional
from bs4 import BeautifulSoup
import requests
from jinja2 import Template

from nachricht.llm import query_llm

from ..config import Config
from ..notes import Language


logger = logging.getLogger(__name__)


async def translate(
    text: str, src_language: Language, dst_language: Language
) -> str:
    """
    Translate text from a source language to a destination language using LLM.

    Args:
        text (str): The text to translate.
        src_language (Language): The source language of the text.
        dst_language (Language): The target language for the translation.

    Returns:
        str: The translated text.
    """

    logger.info(
        "Translating text from '%s' to '%s': '%s'",
        src_language.name,
        dst_language.name,
        text,
    )

    instructions_template = Template(
        """
Translate the following text from {{ src_language }} to {{ dst_language }}.
Ensure the translation captures the original meaning as accurately as possible.
"""
    )
    instructions = instructions_template.render(
        src_language=src_language.name, dst_language=dst_language.name
    )

    translation = await query_llm(instructions, text)
    logger.info("Received translation: '%s'", translation)
    return translation


async def get_explanation(
    input: str,
    src_language: Language,
    dst_language: Optional[Language] = None,
    notes: Optional[list] = None,
    context: Optional[str] = None,
) -> str:
    """
    Request an explanation for a word in a specified language.

    Args:
        input (str): The word or phrase to explain.
        src_language (Language): The source language of the input word.
        dst_language (Language, optional): The target language for the explanation. Defaults to the source language.
        notes (list, optional): Additional notes for context. Defaults to None.
        context (str, optional): Additional context for the explanation. Defaults to None.

    Returns:
        str: The explanation of the word or phrase.
    """
    if not dst_language:
        dst_language = src_language

    logger.info(
        "Requesting explanation for input: '%s' (%s) in language: '%s'",
        input,
        src_language.name,
        dst_language.name,
    )

    instructions_template = Template(
        src_language.get_config("prompts.explanation")
    )
    instructions = instructions_template.render(
        src_language=src_language.name, dst_language=dst_language.name
    )

    if notes:
        instructions += f"Integrate these words when relevant: {', '.join(note.field1 for note in notes)}.\n"

    if context:
        instructions += f"Consider this context for the word: '{context}'.\n"

    logger.debug(
        f"Requesting explanation for {input} with instructions\n: {instructions}"
    )
    model = src_language.get_config("models.explanation")
    explanation = await query_llm(instructions, input, model=model)
    logger.info("Received explanation: '%s'", explanation)
    return explanation


async def get_recap(url, language: Language, notes: Optional[list] = None):
    """
    Fetch the content of a URL and request a summary recap in a specific language.

    Args:
        url (str): The URL of the content to summarize.
        language (Language): The target language for the summary.
        notes (list, optional): Additional words to integrate into the recap. Defaults to None.

    Returns:
        str: The summarized recap of the content in the specified language.
    """
    logger.info("Fetching URL content for recap: %s", url)

    response = requests.get(url)
    response.raise_for_status()
    soup = BeautifulSoup(response.content, "html.parser")

    text_content = " ".join(p.get_text() for p in soup.find_all("p"))
    logger.info("Fetched text content from URL.")

    instructions_template = Template(language.get_config("prompts.recap"))
    instructions = instructions_template.render(language=language.name)

    if notes:
        instructions += """
- Integrate the following words into the text: %s. Feel free to change their form and to use their derivatives.
- Mark those and ONLY those words in text with single underscores: _word_.
""" % ", ".join(
            [note.field1 for note in notes]
        )

    logger.info("Requesting recap for text from URL: %s", url)
    logger.debug("Recap instructions:\n%s", instructions)
    model = language.get_config("models.recap")
    recap = await query_llm(instructions, text_content, model=model)
    logger.info("Received recap: '%s'", recap)
    return recap


async def get_base_form(input: str, language: Language) -> str:
    """
    Request the base form of a word in a specified language.

    Args:
        input (str): The word or phrase to convert to its base form.
        language (Language): The language of the input word.

    Returns:
        str: The base form of the word or phrase.
    """

    logger.info(
        "Requesting base form for input: '%s' in language: '%s'",
        input,
        language.name,
    )
    if not language.get_config("features.base_form", default=True):
        return input

    instructions_template = Template(language.get_config("prompts.base_form"))
    instructions = instructions_template.render(language=language.name)

    logger.debug(
        f"Requesting base form for {input} with instructions:\n{instructions}"
    )
    model = language.get_config("models.base_form")
    base_form = await query_llm(instructions, input, model=model)
    logger.info("Received base form: '%s'", base_form)
    return base_form


async def find_mistakes(
    input: str, src_language: Language, dst_language: Language
) -> str:
    """
    Request LLM to find up to 3 main language mistakes in a text, explain them, and provide correct versions.

    Args:
        input (str): The text with potential mistakes.
        src_language (Language): The language of the input text.
        dst_language (Language): The language for the explanation of mistakes.

    Returns:
        str: A numbered list of mistakes with explanations and corrections.
    """
    logger.info(
        "Requesting mistake analysis for input: '%s' (source lang: '%s', explanation lang: '%s')",
        input,
        src_language.name,
        dst_language.name,
    )
    instructions_template = Template(
        src_language.get_config("prompts.mistakes")
    )
    instructions = instructions_template.render(
        src_language=src_language.name,
        dst_language=dst_language.name,
    )

    logger.debug(
        f"Requesting mistake analysis for '{input}' with instructions:\n{instructions}"
    )

    model = src_language.get_config(
        "models.mistakes", src_language.get_config("models.default")
    )
    mistake_analysis = await query_llm(instructions, input, model=model)
    logger.info("Received mistake analysis: '%s'", mistake_analysis)
    return mistake_analysis


async def get_clarification(
    text: str, language: Language, native_language: Language
):
    instructions_template = Template(
        language.get_config("prompts.clarification")
    )
    instructions = instructions_template.render(
        language=language.name, native_language=native_language.name
    )
    model = language.get_config("models.clarification")
    return await query_llm(instructions, text, model=model)


async def get_usage_examples(
    note, native_language: Language, examples: list = []
) -> str:
    language = note.language
    instructions_template = Template(language.get_config("prompts.examples"))
    instructions = instructions_template.render(
        language=language.name,
        native_language=native_language.name,
        examples=examples,
    )
    model = language.get_config("models.examples")
    return await query_llm(instructions, note.field1, model=model)
