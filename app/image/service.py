import os
import hashlib
import logging
from asyncio import to_thread

from PIL import Image

import vertexai
from vertexai.preview.vision_models import ImageGenerationModel

from ..config import Config
from ..srs import Note


logger = logging.getLogger(__name__)

vertexai.init(
    project=Config.IMAGE["vertexai_project_id"], location="us-central1"
)


async def generate_image(description: str, force: bool = False) -> str:
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
    small_image_path = os.path.join(
        "data", "images", f"small.{description_hash}.jpg"
    )

    if os.path.exists(small_image_path) and not force:
        logger.info("Cached small image found, returning it.")
        return small_image_path

    if os.path.exists(image_path) and not force:
        logger.info("Large image found without small version, resampling.")
        _resample_image(image_path, small_image_path)
        return small_image_path

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
    response = await to_thread(
        image_model.generate_images,
        prompt=prompt,
        number_of_images=1,
        aspect_ratio="16:9",
        safety_filter_level="block_some",
        person_generation="allow_all",
    )
    logger.info("Image generation completed.")

    # Save the original image
    response.images[0].save(image_path)
    logger.info("Original image saved at: %s", image_path)

    # Downsample the original image
    _resample_image(image_path, small_image_path)

    logger.info("Downsampled image saved at: %s", small_image_path)

    return small_image_path


def _resample_image(image_path: str, small_image_path: str) -> None:
    with Image.open(image_path) as img:
        original_size = img.size
        img = img.resize(
            (original_size[0] // 2, original_size[1] // 2), Image.LANCZOS
        )
        img.save(small_image_path, quality=60)
