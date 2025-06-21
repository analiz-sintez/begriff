from typing import (
    Optional,
    Callable,
    TypeAlias,
    TypeVar,
    ParamSpec,
    Concatenate,
)
import logging
from inspect import signature, Signature, Parameter

from telegram.ext import CallbackContext
from telegram.constants import ParseMode
from telegram import (
    Update,
    InputMediaPhoto,
)


P = ParamSpec("P")
R = TypeVar("R")


from ..config import Config
from ..core import get_user, User


logger = logging.getLogger(__name__)

UserInjector: TypeAlias = Callable[
    [Callable[Concatenate[User, P], R]], Callable[Concatenate[Update, P], R]
]


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
        async def wrapped(update: Update, **kwargs):
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
            kwargs["user"] = user
            logger.info(kwargs.keys())
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
