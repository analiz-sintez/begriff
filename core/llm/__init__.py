import logging
from typing import Optional
from asyncio import to_thread
from openai import OpenAI


logger = logging.getLogger(__name__)

_client = None
_default_model = None


def init_llm_client(host: str, api_key: str, default_model: str) -> OpenAI:
    global _client
    global _default_model
    _client = OpenAI(base_url=host, api_key=api_key)
    _default_model = default_model
    return _client


async def query_llm(
    instructions: str,
    input: str,
    model: Optional[str] = None,
    client: Optional[OpenAI] = None,
) -> str:
    global _default_model
    global _client

    if client is None:
        client = _client

    assert client is not None

    if model is None:
        model = _default_model

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

    translation = await query_llm(instructions, text)
    logger.info("Received translation: '%s'", translation)
    return translation
