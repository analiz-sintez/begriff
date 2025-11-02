import logging

from dataclasses import dataclass
from jinja2 import Template

from nachricht.auth import User
from nachricht.bus import Signal
from nachricht.messenger import Context, Emoji, Message
from nachricht.i18n import TranslatableString as _

from app.notes.example_note import add_example_for

from .. import bus, router, Config
from ..notes import (
    WordNote,
    examples_for,
)
from ..srs import (
    get_note,
    Note,
    format_explanation,
)

from .study import ImageGenerated, generate_image_for_note


logger = logging.getLogger(__name__)


################################################################
# Sharable post


@dataclass
class SharablePostRequested(Signal):
    """A user requires a sharable post for a word."""

    note_id: int


@dataclass
class SharablePostDownvoted(Signal):
    """A user disliked the image on the sharable post and wants to regenerate it."""

    note_id: int


async def _make_sharable_post(note: Note) -> str:
    template = Template(Config.TEMPLATES["sharable_post"])
    text = template.render(
        word=note.field1,
        explanation=format_explanation(note.field2),
        examples=examples_for(note),
    )
    return text


# TODO refactor this: DRY
@bus.on(SharablePostRequested)
@router.authorize()
async def handle_sharable_post_request(ctx: Context, user: User, note_id: int):
    note = get_note(note_id)
    if not isinstance(note, WordNote):
        logger.error(f"Sharable post requested for a non-word note {note_id}")
        return

    image_path = await note.get_image(hi_res=True)

    is_admin = user.login in ctx.config.AUTHENTICATION["admin_logins"]
    if not image_path and is_admin:
        logger.info(
            f"Admin {user.login} requested sharable post for note {note.id} with no image. Generating one."
        )
        try:
            await generate_image_for_note(note)
            bus.emit(ImageGenerated(note.id))
            image_path = await note.get_image(hi_res=True)
        except Exception as e:
            logger.error(f"Failed to generate image for note {note_id}: {e}")
            await ctx.send_message(
                _(
                    "Sorry, I couldn't generate an image for this word right now."
                )
            )

    for _ in range(3 - len(examples_for(note))):
        await add_example_for(note)

    message_text = await _make_sharable_post(note)
    on_reaction = {Emoji.THUMBSDOWN: SharablePostDownvoted(note_id=note.id)}

    await ctx.send_message(
        text=message_text,
        image=image_path,
        on_reaction=on_reaction,
        new=True,
    )


@bus.on(SharablePostDownvoted)
@router.authorize(admin=True)
async def regenerate_sharable_post_image(
    ctx: Context, user: User, note_id: int, reply_to: Message
):
    note = get_note(note_id)
    if not isinstance(note, WordNote):
        return

    logger.info(
        f"User {user.login} requested image regeneration for note {note_id}"
    )

    try:
        await generate_image_for_note(note, force=True)
        bus.emit(ImageGenerated(note.id))
        image_path = await note.get_image(hi_res=True)
    except Exception as e:
        logger.error(f"Failed to regenerate image for note {note_id}: {e}")
        await ctx.send_message(
            _("Sorry, I couldn't regenerate the image right now."), new=True
        )
        return

    message_text = await _make_sharable_post(note)
    on_reaction = {Emoji.THUMBSDOWN: SharablePostDownvoted(note_id=note.id)}

    await ctx.send_message(
        text=message_text, image=image_path, on_reaction=on_reaction, new=False
    )
