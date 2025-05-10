"""

    Yfirlestur: Online spelling and grammar correction for Icelandic

    Copyright (C) 2020-2025 Miðeind ehf.

    This software is licensed under the MIT License:

        Permission is hereby granted, free of charge, to any person
        obtaining a copy of this software and associated documentation
        files (the "Software"), to deal in the Software without restriction,
        including without limitation the rights to use, copy, modify, merge,
        publish, distribute, sublicense, and/or sell copies of the Software,
        and to permit persons to whom the Software is furnished to do so,
        subject to the following conditions:

        The above copyright notice and this permission notice shall be
        included in all copies or substantial portions of the Software.

        THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
        EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
        MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
        IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY
        CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT,
        TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE
        SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.


    This module describes the SQLAlchemy models for the database.

"""

from typing import Any, Optional, cast

from datetime import datetime

from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import (
    Column,
    Integer,
    String,
    Float,
    DateTime,
    Sequence,
    Boolean,
    UniqueConstraint,
    Index,
    ForeignKey,
    func,
    text,
)
from sqlalchemy.orm import relationship, backref  # type: ignore
from sqlalchemy.ext.hybrid import Comparator, hybrid_property
from sqlalchemy.dialects.postgresql import UUID as psql_UUID
from sqlalchemy.orm.relationships import RelationshipProperty


class CaseInsensitiveComparator(Comparator):
    """Boilerplate from the PostgreSQL documentation to implement
    a case-insensitive comparator"""

    # See https://docs.sqlalchemy.org/en/13/orm/extensions/hybrid.html

    def __eq__(self, other: object) -> bool:  # type: ignore
        return func.lower(self.__clause_element__()) == func.lower(other)  # type: ignore


# Create the SQLAlchemy ORM Base class
Base: Any = declarative_base()

# Add a table() function to the Base class, returning the __table__ member.
# Note that this hack is necessary because SqlAlchemy doesn't readily allow
# intermediate base classes between Base and the concrete table classes.
setattr(Base, "table", classmethod(lambda cls: cls.__table__))


class Entity(Base):
    """Represents a named entity"""

    __tablename__ = "entities"

    # Primary key
    id = Column(Integer, Sequence("entities_id_seq"), primary_key=True)

    # Foreign key to an article
    article_url = Column(
        String,
        # We don't delete associated persons if the article is deleted
        ForeignKey("articles.url", onupdate="CASCADE", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )

    # Name
    name = cast(str, Column(String, index=True))

    @hybrid_property
    def name_lc(self) -> str:  # type: ignore
        return self.name.lower()

    @name_lc.comparator  # type: ignore
    def name_lc(cls):  # pylint: disable=no-self-argument
        return CaseInsensitiveComparator(cls.name)

    # Verb ('er', 'var', 'sé')
    verb = cast(str, Column(String, index=True))
    # Entity definition
    definition = cast(str, Column(String, index=True))

    # Authority of this fact, 1.0 = most authoritative, 0.0 = least authoritative
    authority = cast(float, Column(Float))

    # Timestamp of this entry
    timestamp = cast(datetime, Column(DateTime))

    # The back-reference to the Article parent of this Entity
    # Modify this to RelationshipProperty[Article] once Pylance, Mypy and Python 3.6
    # settle their differences
    article: RelationshipProperty = relationship(  # type: ignore
        "Article", backref=backref("entities", order_by=name)  # type: ignore
    )

    # Add an index on the entity name in lower case
    name_lc_index = Index("ix_entities_name_lc", func.lower(name))

    def __repr__(self):
        return "Entity(id='{0}', name='{1}', verb='{2}', definition='{3}')".format(
            self.id, self.name, self.verb, self.definition
        )


class Correction(Base):
    """Represents correction feedback"""

    __tablename__ = "corrections"

    # Primary key (UUID)
    id = Column(
        psql_UUID(as_uuid=False),
        server_default=text("uuid_generate_v1()"),
        primary_key=True,
    )

    # Timestamp of this entry
    timestamp = cast(datetime, Column(DateTime, nullable=False, index=True))

    # The original sentence being annotated
    sentence = cast(str, Column(String, nullable=False))

    # Annotation code
    code = cast(str, Column(String(32), nullable=False, index=True))

    # Annotation text
    annotation = cast(str, Column(String, nullable=False))

    # Annotation span
    start = cast(int, Column(Integer, nullable=False))
    end = cast(int, Column(Integer, nullable=False))

    # Correction
    correction = cast(str, Column(String, nullable=False))

    # User feedback
    feedback = cast(str, Column(String(32), nullable=False, index=True))

    # Reason text
    reason = cast(str, Column(String(32), index=True))

    def __repr__(self) -> str:
        return "Correction(id='{0}', sent='{1}', code='{2}', annotation='{3}', feedback='{4}')".format(
            self.id, self.sentence, self.code, self.annotation, self.feedback
        )
