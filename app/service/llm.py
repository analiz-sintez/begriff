import os
from openai import OpenAI

def get_explanation(input, language):
    client = OpenAI(
        api_key=os.environ.get("OPENAI_API_KEY")
    )

    response = client.responses.create(
        model="gpt-4o-mini",
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
        input=input
    )
    return response

# Example usage:
# explanation = get_explanation("demise", "English")
