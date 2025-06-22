import logging
from typing import Optional
from asyncio import to_thread
from openai import OpenAI
from ..config import Config
from bs4 import BeautifulSoup
import requests

# Set up logging

logger = logging.getLogger(__name__)

client = OpenAI(base_url=Config.LLM["host"], api_key=Config.LLM["api_key"])


async def _query_llm(
    instructions: str, input: str, model: Optional[str] = None
) -> str:
    if model is None:
        model = Config.LLM["models"]["default"]

    assert model is not None

    response = await to_thread(
        client.chat.completions.create,
        model=model,
        messages=[
            {"role": "system", "content": instructions},
            {"role": "user", "content": input},
        ],
    )
    result = response.choices[0].message.content.strip()
    return result


async def get_explanation(
    input: str,
    src_language: str,
    dst_language: Optional[str] = None,
    notes: Optional[list] = None,
    context: Optional[str] = None,
) -> str:
    """
    Request an explanation for a word in a specified language.

    Args:
        input (str): The word or phrase to explain.
        src_language (str): The source language of the input word.
        dst_language (str, optional): The target language for the explanation. Defaults to the source language.
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
        src_language,
        dst_language,
    )

    instructions = f"""
You are an expert linguist tasked with explaining words in simple terms. You must explain the given {src_language} word or phrase in {dst_language} using the following guidelines:

- Avoid using the exact word or phrase in the explanation.
- Only treat the word as a verb if preceded by 'to'.
- Keep the explanation concise, fitting it on one line without using empty lines or the ';' symbol, using '.' instead.
- Indicate any special contextual use (e.g., official documents, office slang, street slang) in square brackets.
- If a word has multiple significant meanings, provide explanations for the two most common contexts.
- The explanation should be entirely in {dst_language}.

Example 1 (for English).
Prompt: to gorge
Reply: To eat a large amount quickly.

Example 2 (for English).
Prompt: fixer
Reply: [General] Someone who solves problems, often in a quick or discreet manner. [Informal/Slang] A person who helps others by arranging things behind the scenes, especially in politics or media.    
"""

    if notes:
        instructions += f"Integrate these words when relevant: {', '.join(note.field1 for note in notes)}.\n"

    if context:
        instructions += f"Consider this context for the word: '{context}'.\n"

    logger.debug(
        f"Requesting explanation for {input} with instructions\n: {instructions}"
    )

    explanation = await _query_llm(
        instructions, input, model=Config.LLM["models"]["explanation"]
    )
    logger.info("Received explanation: '%s'", explanation)
    return explanation


async def get_recap(url, language, notes: Optional[list] = None):
    """
    Fetch the content of a URL and request a summary recap in a specific language.

    Args:
        url (str): The URL of the content to summarize.
        language (str): The target language for the summary.
        notes (list, optional): Additional words to integrate into the recap. Defaults to None.

    Returns:
        str: The summarized recap of the content in the specified language.
    """
    logger.info("Fetching URL content for recap: %s", url)

    response = requests.get(url)
    response.raise_for_status()
    soup = BeautifulSoup(response.content, "html.parser")

    # Extract text from paragraphs
    text_content = " ".join(p.get_text() for p in soup.find_all("p"))
    logger.info("Fetched text content from URL.")

    instructions = f"""
You are {language} tutor helping a student to learn new language. The student studies new words using flashcards, so it would be beneficial for them to see the words in use in real text.

Please summarize the following text into one paragraph using simple {language}.

Instructions:
- Create one concise paragraph of 100-150 words.
- Use simple language, and write only in {language}.
- Keep the summary simple and clear."""

    if notes:
        instructions += """
- Integrate the following words into the text: %s. Feel free to change their form and to use their derivatives.
- Mark those and ONLY those words in text with single underscores: _word_.
""" % ", ".join(
            [note.field1 for note in notes]
        )

    logger.info("Requesting recap for text from URL: %s", url)
    logger.debug("Recap instructions:\n%s", instructions)

    recap = await _query_llm(
        instructions, text_content, model=Config.LLM["models"]["recap"]
    )
    logger.info("Received recap: '%s'", recap)
    return recap


async def get_base_form(input: str, language: str) -> str:
    """
    Request the base form of a word in a specified language.

    Args:
        input (str): The word or phrase to convert to its base form.
        language (str): The language of the input word.

    Returns:
        str: The base form of the word or phrase.
    """

    logger.info(
        "Requesting base form for input: '%s' in language: '%s'",
        input,
        language,
    )

    instructions = f"""
Please convert the following {language} word or phrase to its base form (e.g., infinitive for verbs, singular for nouns).

Instructions:
- Return the word in its base form.
- If the word is already in its base form, return it as is.
"""

    logger.debug(
        f"Requesting base form for {input} with instructions:\n{instructions}"
    )

    base_form = await _query_llm(
        instructions, input, model=Config.LLM["models"]["base_form"]
    )
    logger.info("Received base form: '%s'", base_form)
    return base_form


async def translate(
    text: str, src_language: str, dst_language: str = "English"
) -> str:
    """
    Translate text from a source language to a destination language using LLM.

    Args:
        text (str): The text to translate.
        src_language (str): The source language of the text.
        dst_language (str, optional): The target language for the translation. Defaults to English.

    Returns:
        str: The translated text.
    """

    logger.info(
        "Translating text from '%s' to '%s': '%s'",
        src_language,
        dst_language,
        text,
    )

    instructions = f"""
Translate the following text from {src_language} to {dst_language}.
Ensure the translation captures the original meaning as accurately as possible.
"""

    translation = await _query_llm(instructions, text)
    logger.info("Received translation: '%s'", translation)
    return translation


async def find_mistakes(
    input: str, src_language: str, dst_language: str
) -> str:
    """
    Request LLM to find up to 3 main language mistakes in a text, explain them, and provide correct versions.

    Args:
        input (str): The text with potential mistakes.
        src_language (str): The language of the input text.
        dst_language (str): The language for the explanation of mistakes.

    Returns:
        str: A numbered list of mistakes with explanations and corrections.
    """
    logger.info(
        "Requesting mistake analysis for input: '%s' (source lang: '%s', explanation lang: '%s')",
        input,
        src_language,
        dst_language,
    )

    instructions = f"""
You are a language tutor. A student has written the following text in {src_language}.
Please identify up to 3 main grammatical or lexical mistakes in their text.
For each mistake:
1. Briefly explain the mistake in {dst_language}.
2. Provide the corrected version of the problematic part of the sentence in {src_language}.

Present your findings as a numbered list.
If there are no mistakes, or if the text is too short to analyze, simply state that in {dst_language}.

Example for a student writing in English (and explanations in English):
Student's text: "I will can go to the cinema tomorrow."
Your response:
1. Incorrect modal verb usage: You cannot use "will" and "can" together.
   Corrected: "I will be able to go to the cinema tomorrow." or "I can go to the cinema tomorrow."

Student's text: "He go to school every day."
Your response:
1. Subject-verb agreement error: The verb "go" should be "goes" for the third-person singular pronoun "He".
   Corrected: "He goes to school every day."
"""

    logger.debug(
        f"Requesting mistake analysis for '{input}' with instructions:\n{instructions}"
    )

    # Consider adding a specific model for mistake detection in Config if needed
    # e.g., model=Config.LLM["models"]["mistakes"]
    mistake_analysis = await _query_llm(
        instructions,
        input,
        model=Config.LLM["models"].get("mistakes")
        or Config.LLM["models"]["default"],
    )
    logger.info("Received mistake analysis: '%s'", mistake_analysis)
    return mistake_analysis
