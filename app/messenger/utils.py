from typing import (
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
from telegram import Update


P = ParamSpec("P")
R = TypeVar("R")


logger = logging.getLogger(__name__)

from ..config import Config
from ..core import get_user, User

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
