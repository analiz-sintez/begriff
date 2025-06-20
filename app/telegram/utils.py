from typing import Optional
import logging
from telegram.ext import CallbackContext
from telegram.constants import ParseMode
from telegram import (
    Update,
    InputMediaPhoto,
)
from ..config import Config

logger = logging.getLogger(__name__)


async def send_message(
    update: Update,
    context: CallbackContext,
    caption: str,
    markup=None,
):
    """Send or update message, without image."""
    reply_fn = (
        update.callback_query.edit_message_text
        if update.callback_query is not None
        else update.message.reply_text
    )
    await reply_fn(caption, reply_markup=markup, parse_mode=ParseMode.MARKDOWN)


async def send_image_message(
    update: Update,
    context: CallbackContext,
    caption: str,
    image: Optional[str] = None,
    markup=None,
):
    """Send or update photo message."""
    if not Config.IMAGE["enable"]:
        logger.info("Images in study mode are disabled, ignoring them.")
        await send_message(update, context, caption, markup)
    elif update.callback_query is not None:
        # If the session continues, edit photo object.
        message = (
            update.callback_query.message
            if update.message is None
            else update.message
        )
        if image:
            await message.edit_media(
                media=InputMediaPhoto(
                    media=open(image, "rb"),
                    caption=caption,
                    parse_mode=ParseMode.MARKDOWN,
                ),
                reply_markup=markup,
            )
        else:
            await message.edit_caption(
                caption=caption,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=markup,
            )
    else:
        # If the session just starts, send photo object.
        await context.bot.send_photo(
            chat_id=update.effective_chat.id,
            photo=open(image, "rb") if image else None,
            caption=caption,
            reply_markup=markup,
            parse_mode=ParseMode.MARKDOWN,
        )
