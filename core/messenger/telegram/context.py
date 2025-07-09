from typing import Optional, Dict
import logging

from telegram.ext import CallbackContext
from telegram.constants import ParseMode
from telegram import (
    Update,
    InputMediaPhoto,
    Message,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)

from ...bus import encode
from .. import Context, Button, Keyboard


logger = logging.getLogger(__name__)


def make_button(button: Button) -> InlineKeyboardButton:
    return InlineKeyboardButton(
        button.text, callback_data=encode(button.callback)
    )


def make_keyboard(keyboard: Keyboard) -> InlineKeyboardMarkup:
    buttons = [[make_button(b) for b in row] for row in keyboard.buttons]
    return InlineKeyboardMarkup(buttons)


class TelegramContext(Context):
    def __init__(
        self,
        update: Update,
        context: CallbackContext,
        config: Optional[object] = None,
    ):
        self.update = update
        self.context = context
        return super().__init__(config)

    def username(self) -> str:
        return self.update.effective_user.username

    @property
    def message_context(self) -> Dict[int, Dict]:
        """
        A store of per-message metadata. e.g. a note bound to the message
        to perform context actions on it.
        """
        if "_message_context" not in self.context.chat_data:
            self.context.chat_data["_message_context"]: Dict[int, Dict] = {}
        return self.context.chat_data["_message_context"]

    async def _send_message(
        self,
        update: Update,
        context: CallbackContext,
        text: str,
        markup=None,
        image: Optional[str] = None,
        new: bool = False,
        reply_to: Optional[Message] = None,
    ):
        """Send or update a message, with or without an image."""
        if image and not self.config.IMAGE["enable"]:
            logger.info(
                "Images are disabled in config, sending message without image."
            )
            image = None  # Force no image if disabled

        can_edit = update.callback_query is not None and not new

        if can_edit:
            # Editing an existing message
            message = update.callback_query.message
            if image:
                try:
                    await message.edit_media(
                        media=InputMediaPhoto(
                            media=open(image, "rb"),
                            caption=text,
                            parse_mode=ParseMode.MARKDOWN,
                        ),
                        reply_markup=markup,
                    )
                except (
                    Exception
                ) as e:  # If image is the same, telegram might raise an error.
                    # Try editing caption instead.
                    logger.warning(
                        f"Failed to edit media (possibly same image): {e}. Trying to edit caption."
                    )
                    await message.edit_caption(
                        caption=text,
                        parse_mode=ParseMode.MARKDOWN,
                        reply_markup=markup,
                    )
            else:
                # If there was an image before, and now we send without,
                # we must edit_message_text, not edit_caption.
                # However, if there was no image, edit_caption would fail.
                # The safest is to try edit_message_text, and if it fails (e.g. was photo),
                # then try to edit_caption (to remove image, we'd need to send new message).
                # For simplicity, if no image now, assume we're editing text part or sending text only.
                # This might require deleting the old message and sending a new one if media type changes from photo to text.
                # For now, let's assume we can edit the text or caption.
                try:
                    await message.edit_text(  # Handles case where previous message was text
                        text=text,
                        reply_markup=markup,
                        parse_mode=ParseMode.MARKDOWN,
                    )
                except (
                    Exception
                ):  # Fallback to edit_caption if edit_text fails (e.g. previous was photo)
                    await message.edit_caption(
                        caption=text,
                        parse_mode=ParseMode.MARKDOWN,
                        reply_markup=markup,
                    )
        else:
            # Sending a new message
            effective_reply_to_message_id = None
            if reply_to and isinstance(reply_to, Message):
                effective_reply_to_message_id = reply_to.message_id
            elif (
                update.message
            ):  # Default reply if `update.message` exists and no explicit `reply_to`
                effective_reply_to_message_id = update.message.message_id

            if image:
                message = await context.bot.send_photo(
                    chat_id=update.effective_chat.id,
                    photo=open(image, "rb"),
                    caption=text,
                    reply_markup=markup,
                    parse_mode=ParseMode.MARKDOWN,
                    reply_to_message_id=effective_reply_to_message_id,
                )
            else:
                message = await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text=text,
                    reply_markup=markup,
                    parse_mode=ParseMode.MARKDOWN,
                    reply_to_message_id=effective_reply_to_message_id,
                )
        return message

    async def send_message(
        self,
        text: str,
        markup: Optional[Keyboard] = None,
        image: Optional[str] = None,
        new: bool = False,
        reply_to: Optional[Message] = None,
    ):
        return await self._send_message(
            self.update,
            self.context,
            text,
            image=image,
            markup=make_keyboard(markup) if markup else None,
            new=new,
            reply_to=reply_to,
        )
