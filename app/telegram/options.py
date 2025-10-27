from nachricht.auth import User
from nachricht.messenger import Context
from nachricht.i18n import TranslatableString as _

from nachricht.messenger.options import ShowOptionGroup

from .. import bus, router


@router.command("options", description=_("Configure your personal settings."))
@router.authorize()
async def options_command(ctx: Context, user: User):
    # We start at the root for the current user.
    signal = ShowOptionGroup(obj_type="User", obj_id=user.id, path="")
    await bus.emit_and_wait(signal, ctx=ctx)
