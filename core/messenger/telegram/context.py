from typing import Optional, List, Dict, Union
import logging

from babel import Locale
from telegram.ext import CallbackContext
from telegram.constants import ParseMode
from telegram import (
    Update,
    InputMediaPhoto,
    Message as PTBMessage,
    Chat as PTBChat,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)

from ...auth import User, get_user
from ...bus import Signal, encode
from .. import Context, Button, Keyboard, Account, Message, Chat, Emoji
from ...i18n import TranslatableString, resolve


logger = logging.getLogger(__name__)


class TelegramContext(Context):
    def __init__(
        self,
        update: Update,
        context: CallbackContext,
        config: Optional[object] = None,
    ):
        self._update = update
        self._context = context
        return super().__init__(config)

    def username(self) -> str:
        return self.account.login

    @property
    def account(self) -> Account:
        """The messenger account which initiated an update."""
        if not hasattr(self, "_account"):
            tg_user = self._update.effective_user
            try:
                locale = Locale.parse(tg_user.language_code)
            except Exception as e:
                logger.error("Wrong locale: account %s, error %s", tg_user, e)
                locale = Locale("en")
            self._account = Account(
                id=tg_user.id,
                login=tg_user.username,
                locale=locale,
                _=tg_user,
            )
        return self._account

    @property
    def user(self) -> User:
        """The app user which initiated an update."""
        if not hasattr(self, "_user"):
            self._user = get_user(login=self.account.login)
        return self._user

    @property
    def locale(self) -> Locale:
        """Locale to use for the interface."""
        if user_language_code := self.user.get_option("locale"):
            return Locale.parse(user_language_code)
        elif account_locale := self.account.locale:
            return account_locale
        else:
            return Locale("en")

    @property
    def message(self) -> Optional[Message]:
        """The message the user sent."""
        if not hasattr(self, "_message"):
            if tg_message := self._update.message:
                self._message = Message(
                    id=tg_message.message_id,
                    chat_id=tg_message.chat.id,
                    user_id=tg_message.from_user.id,
                    text=tg_message.text,
                    _=tg_message,
                )
                if tg_reply_to := tg_message.reply_to_message:
                    parent = Message(
                        id=tg_reply_to.message_id,
                        chat_id=tg_reply_to.chat.id,
                        user_id=tg_reply_to.from_user.id,
                        text=tg_reply_to.text,
                        _=tg_reply_to,
                    )
                    self._message.parent = parent
            else:
                self._message = None
        return self._message

    def context(self, obj: Union[Message, Chat, Account]) -> Dict:
        """
        All this is from current user perspective. Multiple users
        can have different contexts on the same messages, chats and
        other users.

        Message: message context;
        Chat: chat context;
        User: user context, including a context of one user on another one.
        """
        if isinstance(obj, Message):
            # Message context is stored in chats telegram context
            store = self._context.chat_data
            key = "_messages"
        elif isinstance(obj, Chat):
            # Message context is stored in users telegram context
            store = self._context.user_data
            key = "_chats"
        elif isinstance(obj, Account):
            # Users context is stored in users telegram context
            store = self._context.user_data
            key = "_users"
        else:
            raise TypeError(f"Unsupported type: {type(obj)}.")

        # ... create the context storage if missing
        if key not in store:
            store[key]: Dict[int, Dict] = {}
        ctx = store[key]

        # ... create the dict for the given object if missing
        if obj.id not in ctx:
            ctx[obj.id]: Dict = {}

        return ctx[obj.id]

    async def _send_message(
        self,
        update: Update,
        context: CallbackContext,
        text: str,
        markup=None,
        image: Optional[str] = None,
        new: bool = False,
        reply_to: Optional[Union[PTBMessage, bool]] = None,
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
                # If there was an image before, and now we send without an image,
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
            if isinstance(reply_to, PTBMessage):
                effective_reply_to_message_id = reply_to.message_id
            elif type(reply_to) is bool and reply_to and update.message:
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

    async def _make_button(self, button: Button) -> InlineKeyboardButton:
        if isinstance(button.text, TranslatableString):
            text = await resolve(button.text, self.locale)
        else:
            text = str(button.text)
        return InlineKeyboardButton(
            text, callback_data=encode(button.callback)
        )

    async def _make_keyboard(self, keyboard: Keyboard) -> InlineKeyboardMarkup:
        buttons = [
            [await self._make_button(b) for b in row]
            for row in keyboard.buttons
        ]
        return InlineKeyboardMarkup(buttons)

    async def send_message(
        self,
        text: Union[str, TranslatableString],
        markup: Optional[Keyboard] = None,
        image: Optional[str] = None,
        new: bool = False,
        reply_to: Optional[Union[Message, bool]] = None,
        on_reply: Optional[Signal] = None,
        on_reaction: Optional[Dict[Emoji, Union[Signal, List[Signal]]]] = None,
        on_command: Optional[Dict[str, Union[Signal, List[Signal]]]] = None,
        context: Optional[Dict] = None,
    ):
        if on_reply:
            # set global on-reply flag — it will trigger from the next message
            self._context.user_data["_on_reply"] = on_reply
        else:
            # remove the global flag as quick as possible
            self._context.user_data["_on_reply"] = None
        if isinstance(text, TranslatableString):
            text = await resolve(text, self.locale)
        tg_message = await self._send_message(
            self._update,
            self._context,
            text,
            image=image,
            markup=await self._make_keyboard(markup) if markup else None,
            new=new,
            reply_to=reply_to._ if isinstance(reply_to, Message) else reply_to,
        )
        message = Message(
            id=tg_message.message_id,
            chat_id=tg_message.chat.id,
            user_id=None,
            text=tg_message.text,
            parent=tg_message.reply_to_message,
            _=tg_message,
        )
        if context:
            self.context(message).update(context)
        if on_reply:
            logger.info("Setting on reply event for message id=%s", message.id)
            self.context(message)["_on_reply"] = on_reply
        if on_reaction:
            logger.debug(
                "Setting reaction handlers for message id=%s", message.id
            )
            self.context(message)["_on_reaction"] = on_reaction
        if on_command:
            logger.debug(
                "Setting command handlers for message id=%s", message.id
            )
            self.context(message)["_on_command"] = on_command
        return message
