import logging
from openai import OpenAI
from ..config import Config

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

client = OpenAI(base_url=Config.LLM["host"], api_key=Config.LLM["api_key"])


def get_explanation(input, language):
    logger.info(
        "Requesting explanation for input: '%s' in language: '%s'",
        input,
        language,
    )
    response = client.responses.create(
        model=Config.LLM["model"],
        instructions=f"""
        Please explain this word in few words in simple {language}.

        Instructions:
        - Don't use this exact word in your explanation.
        - Treat the word as a verb only if there's a \"to\" before it.
        - Try to pack your whole reply in one line. Don't use empty lines between lines. Don't use `;` symbol, use `.` instead.
        - If the word is used in special context (e.g. official documents, office slang, street slang), mention it in square brackets.
        - If there are several contexts, and meanings vary significantly, give meanings for 2 most frequent contexts.
        - The whole response, including context denotions, should be in {language}.

        Example 1.
        Prompt: to gorge
        Reply: To eat a large amount quickly.

        Example 2.
        Prompt: fixer
        Reply: [General] Someone who solves problems, often in a quick or discreet manner. [Informal/Slang] A person who helps others by arranging things behind the scenes, especially in politics or media.    
        """,
        input=input,
    )
    explanation = response.output_text
    logger.info("Received explanation: '%s'", explanation)
    return explanation


# Example usage:
# explanation = get_explanation("demise", "English")
