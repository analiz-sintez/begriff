from datetime import datetime, timezone
from sqlalchemy.orm import mapped_column, Mapped, relationship
from sqlalchemy import Integer, String, ForeignKey, func

from nachricht.db import Model, dttm_utc
from nachricht.auth import User
from .note import Note


class Link(Model):
    __tablename__ = "links"
    id = mapped_column(Integer, primary_key=True)
    ts_created: Mapped[dttm_utc] = mapped_column(
        default=lambda: datetime.now(timezone.utc), server_default=func.now()
    )
    type: Mapped[str] = mapped_column(String(50), index=True)
    __mapper_args__ = {
        "polymorphic_on": "type",
        "polymorphic_identity": "link",
    }
    from_id: Mapped[int] = mapped_column(
        Integer, ForeignKey(Note.id), index=True
    )
    to_id: Mapped[int] = mapped_column(
        Integer, ForeignKey(Note.id), index=True
    )
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey(User.id), index=True
    )

    # # pack of data fields
    # value: Mapped[Optional[float]]
    # text: Mapped[Optional[str]]

    note_from = relationship(Note, foreign_keys=[from_id], backref="out_links")
    note_to = relationship(Note, foreign_keys=[to_id], backref="in_links")
    user = relationship(User, backref="links")
