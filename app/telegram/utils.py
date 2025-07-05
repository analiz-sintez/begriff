from dataclasses import dataclass
from typing import (
    List,
    Optional,
    Callable,
    TypeAlias,
    TypeVar,
    ParamSpec,
    Concatenate,
)
import logging
from inspect import signature, Signature, Parameter
from functools import wraps

from telegram.ext import CallbackContext
from telegram.constants import ParseMode
from telegram import (
    Update,
    InputMediaPhoto,
    Message,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)

from ..bus import Signal, encode


P = ParamSpec("P")
R = TypeVar("R")


from ..config import Config
from ..core import get_user, User


logger = logging.getLogger(__name__)


# TODO this should go to omnibot module
class Context:
    """
    TODO:

    Stores all contextual info, preferably in a messenger-independent
    way. Should support Telegram, Whatsapp, Matrix, Slack, Mattermost,
    maybe even IRC.
    """

    def username(self) -> str:
        pass

    async def message(
        self,
        text: str,
        markup: Optional[object] = None,
        image: Optional[str] = None,
        new: bool = False,
        reply_to: Optional[Message] = None,
    ):
        pass


# TODO this should go to omnibot module
@dataclass
class Button:
    text: str
    callback: Signal


# TODO this should go to omnibot module
@dataclass
class Keyboard:
    buttons: List[List[Button]]


UserInjector: TypeAlias = Callable[
    [Callable[Concatenate[User, P], R]], Callable[Concatenate[Update, P], R]
]


# TODO `authorize` should go to omnibot module, but first decouple it from
# the telegram `Update` in favour of generalized `Context`
def authorize(admin=False) -> UserInjector:
    def _authorize(
        fn: Callable[Concatenate[User, P], R],
    ) -> Callable[Concatenate[Update, P], R]:
        """
        Get a user from telegram update object.
        The inner function should have `user: User` as the first argument,
        but it will not be propagated to the wrapped function (e.g. after
        this decorator, the outer fn will not have `user` arg. In other words,
        `authorize` injects this argument.)
        """
        sig = signature(fn)

        # We require update object, take user info from it,
        # and inject it into the decorated function, so that
        # it doesn't need to bother.
        # TODO config-based authentication.
        @wraps(fn)
        async def wrapped(update: Update, context: CallbackContext, **kwargs):
            if not (user := get_user(update.effective_user.username)):
                raise Exception("Unauthorized.")
            # Authorize the user.
            allowed_logins = Config.AUTHENTICATION["allowed_logins"]
            if allowed_logins and user.login not in allowed_logins:
                raise Exception("Not allowed.")
            if user.login in Config.AUTHENTICATION["blocked_logins"]:
                raise Exception("Blocked.")
            if admin:
                admin_logins = Config.AUTHENTICATION["admin_logins"]
                if user.login not in admin_logins:
                    raise Exception("Only admins allowed.")
            # Inject a user into function.
            kwargs["update"] = update
            kwargs["context"] = context
            kwargs["user"] = user
            new_kwargs = {
                p.name: kwargs[p.name]
                for p in sig.parameters.values()
                if p.name in kwargs
            }
            return await fn(**new_kwargs)

        # Assemble a new signature (bus counts on this info to decide
        # which params to inject)
        params = [p for p in sig.parameters.values()]
        if "update" not in {p.name for p in params}:
            params.append(
                Parameter(
                    "update",
                    Parameter.POSITIONAL_OR_KEYWORD,
                    annotation=Update,
                )
            )
        new_sig = Signature(params)
        wrapped.__signature__ = new_sig
        return wrapped

    return _authorize


async def _send_message(
    update: Update,
    context: CallbackContext,
    caption: str,
    image: Optional[str] = None,
    markup=None,
    new: bool = False,
    reply_to: Optional[Message] = None,
):
    """Internal helper to send or update a message, with or without an image."""
    if image and not Config.IMAGE["enable"]:
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
                        caption=caption,
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
                    caption=caption,
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
                    text=caption,
                    reply_markup=markup,
                    parse_mode=ParseMode.MARKDOWN,
                )
            except (
                Exception
            ):  # Fallback to edit_caption if edit_text fails (e.g. previous was photo)
                await message.edit_caption(
                    caption=caption,
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
            await context.bot.send_photo(
                chat_id=update.effective_chat.id,
                photo=open(image, "rb"),
                caption=caption,
                reply_markup=markup,
                parse_mode=ParseMode.MARKDOWN,
                reply_to_message_id=effective_reply_to_message_id,
            )
        else:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=caption,
                reply_markup=markup,
                parse_mode=ParseMode.MARKDOWN,
                reply_to_message_id=effective_reply_to_message_id,
            )


async def send_message(
    update: Update,
    context: CallbackContext,
    caption: str,
    markup=None,
    image: Optional[str] = None,
    new: bool = False,
    reply_to: Optional[Message] = None,
):
    """Send or update message."""
    await _send_message(
        update,
        context,
        caption,
        image=image,
        markup=markup,
        new=new,
        reply_to=reply_to,
    )


def make_button(button: Button) -> InlineKeyboardButton:
    return InlineKeyboardButton(
        button.text, callback_data=encode(button.callback)
    )


def make_keyboard(keyboard: Keyboard) -> InlineKeyboardMarkup:
    buttons = [[make_button(b) for b in row] for row in keyboard.buttons]
    return InlineKeyboardMarkup(buttons)


class TelegramContext(Context):
    def __init__(self, update: Update, context: CallbackContext):
        self.update = update
        self.context = context

    def username(self) -> str:
        return self.update.effective_user.username

    async def send_message(
        self,
        text: str,
        markup: Optional[Keyboard] = None,
        image: Optional[str] = None,
        new: bool = False,
        reply_to: Optional[Message] = None,
    ):
        return await send_message(
            self.update,
            self.context,
            text,
            image=image,
            markup=make_keyboard(markup) if markup else None,
            new=new,
            reply_to=reply_to,
        )
