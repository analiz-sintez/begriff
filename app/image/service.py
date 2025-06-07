import os
import hashlib
import logging

import vertexai
from vertexai.preview.vision_models import ImageGenerationModel

from ..config import Config
from ..srs import Note


logger = logging.getLogger(__name__)

vertexai.init(
    project=Config.IMAGE["vertexai_project_id"], location="us-central1"
)


def generate_image(description: str, force: bool = False) -> str:
    """
    Generate an image based on the Note's field2 content using Vertex AI, and save it to the ./data/images directory.

    Args:
        description: text content used for image generation.
        force: regenerate image even if it already exists.
    """
    logger.info(
        "Starting image generation process for description: %s", description
    )

    # Generate a hash for the field2 content to use as the image filename
    description_hash = hashlib.md5(description.encode()).hexdigest()
    image_path = os.path.join("data", "images", f"{description_hash}.jpg")

    if os.path.exists(image_path) and not force:
        logger.info("Cached image found, returning it.")
        return image_path

    logger.info("Generated image filename: %s", image_path)

    # Ensure the directory exists
    os.makedirs(os.path.dirname(image_path), exist_ok=True)
    logger.info("Ensured directory exists for the image path.")

    # Load the image generation model
    model_name = Config.IMAGE["model"]
    image_model = ImageGenerationModel.from_pretrained(model_name)
    logger.info("Loaded image generation model: %s", model_name)

    # Generate the image
    prompt = Config.IMAGE["prompt"] % description
    logger.info("Generating image with prompt: %s", prompt)
    response = image_model.generate_images(
        prompt=prompt,
        number_of_images=1,
        aspect_ratio="16:9",
        safety_filter_level="block_some",
        person_generation="allow_all",
    )
    logger.info("Image generation completed.")

    # Save the image to the specified path
    response.images[0].save(image_path)
    logger.info("Image saved at: %s", image_path)

    return image_path
