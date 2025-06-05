import logging
from openai import OpenAI
from ..config import Config
from bs4 import BeautifulSoup
import requests

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

client = OpenAI(base_url=Config.LLM["host"], api_key=Config.LLM["api_key"])


def get_explanation(
    input: str, src_language: str, dst_language: str = None, notes: list = None
):
    if not dst_language:
        dst_language = src_language

    logger.info(
        "Requesting explanation for input: '%s' (%s) in language: '%s'",
        input,
        src_language,
        dst_language,
    )

    instructions = f"""
        Please explain this {src_language} word in few words in simple {dst_language}.

        Instructions:
        - Don't use this exact word in your explanation.
        - Treat the word as a verb only if there's a \"to\" before it.
        - Try to pack your whole reply in one line. Don't use empty lines between lines. Don't use `;` symbol, use `.` instead.
        - If the word is used in special context (e.g. official documents, office slang, street slang), mention it in square brackets.
        - If there are several contexts, and meanings vary significantly, give meanings for 2 most frequent contexts.
        - The whole response, including context denotions, should be in {dst_language}.

        Example 1 (for English).
        Prompt: to gorge
        Reply: To eat a large amount quickly.

        Example 2 (for English).
        Prompt: fixer
        Reply: [General] Someone who solves problems, often in a quick or discreet manner. [Informal/Slang] A person who helps others by arranging things behind the scenes, especially in politics or media.    
"""

    if notes:
        instructions += """
        When appropriate, use the following words in your explanation: %s.
        """ % ", ".join(
            [note.field1 for note in notes]
        )

    logger.info(
        f"Requesting explanation for {input} with instructions\n: {instructions}"
    )

    response = client.responses.create(
        model=Config.LLM["model"],
        instructions=instructions,
        input=input,
    )
    explanation = response.output_text
    logger.info("Received explanation: '%s'", explanation)
    return explanation


def get_recap(url, language, notes: list = None):
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
- Create one concise paragraph.
- Use simple language, and write only in {language}.
- Keep the summary simple and clear."""

    if notes:
        instructions += """
- Integrate the following words into the text: %s. Feel free to change their form and to use their derivatives.
- Mark those and ONLY those words in text with single underscores: _word_.
""" % ", ".join(
            [note.field1 for note in notes]
        )

    logger.info(
        "Requesting recap for text from URL: %s.\nInstructions:\n%s",
        url,
        instructions,
    )

    response = client.responses.create(
        # model=Config.LLM["model"],
        model="chatgpt-4o-latest",
        instructions=instructions,
        input=text_content,
    )
    recap = response.output_text
    logger.info("Received recap: '%s'", recap)
    return recap
