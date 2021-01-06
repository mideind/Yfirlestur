"""

    Greynir: Natural language processing for Icelandic

    Scraper database models

    Copyright (C) 2020 Miðeind ehf.

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


    This module describes the SQLAlchemy models for the scraper database.

"""

from typing import Type

from sqlalchemy import (  # type: ignore
    Table,
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
    PrimaryKeyConstraint,
    func,
    text
)
from sqlalchemy.orm import relationship, backref  # type: ignore
from sqlalchemy.ext.declarative import DeclarativeMeta, declarative_base  # type: ignore
from sqlalchemy.ext.hybrid import Comparator, hybrid_property  # type: ignore
from sqlalchemy.dialects.postgresql import (  # type: ignore
    JSONB, INET, UUID as psql_UUID
)


class CaseInsensitiveComparator(Comparator):

    """ Boilerplate from the PostgreSQL documentation to implement
        a case-insensitive comparator """

    # See https://docs.sqlalchemy.org/en/13/orm/extensions/hybrid.html

    def __eq__(self, other):
        return func.lower(self.__clause_element__()) == func.lower(other)


# Create the SQLAlchemy ORM Base class
Base: DeclarativeMeta = declarative_base()

# Add a table() function to the Base class, returning the __table__ member.
# Note that this hack is necessary because SqlAlchemy doesn't readily allow
# intermediate base classes between Base and the concrete table classes.
setattr(Base, "table", classmethod(lambda cls: cls.__table__))


class Root(Base):
    """ Represents a scraper root, i.e. a base domain and root URL """

    __tablename__ = "roots"

    # Primary key
    id = Column(Integer, Sequence("roots_id_seq"), primary_key=True)

    # Domain suffix, root URL, human-readable description
    domain = Column(String, nullable=False)
    url = Column(String, nullable=False)
    description = Column(String)

    # Default author
    author = Column(String)
    # Default authority of this source, 1.0 = most authoritative, 0.0 = least authoritative
    authority = Column(Float)
    # Finish time of last scrape of this root
    scraped = Column(DateTime, index=True)
    # Module to use for scraping
    scr_module = Column(String(80))
    # Class within module to use for scraping
    scr_class = Column(String(80))
    # Are articles of this root visible on the Greynir web?
    visible = Column(Boolean, default=True)
    # Should articles of this root be scraped automatically?
    scrape = Column(Boolean, default=True)

    # The combination of domain + url must be unique
    __table_args__ = (UniqueConstraint("domain", "url"),)

    def __repr__(self):
        return "Root(domain='{0}', url='{1}', description='{2}')".format(
            self.domain, self.url, self.description
        )


class Article(Base):
    """ Represents an article from one of the roots, to be scraped or having already been scraped """

    __tablename__ = "articles"

    # The article URL is the primary key
    url = Column(String, primary_key=True)

    # UUID
    id = Column(
        psql_UUID(as_uuid=False),
        index=True,
        nullable=False,
        unique=True,
        server_default=text("uuid_generate_v1()"),
    )

    # Foreign key to a root
    root_id = Column(
        Integer,
        # We don't delete associated articles if the root is deleted
        ForeignKey("roots.id", onupdate="CASCADE", ondelete="SET NULL"),
    )

    # Article heading, if known
    heading = Column(String)
    # Article author, if known
    author = Column(String)
    # Article time stamp, if known
    timestamp = Column(DateTime, index=True)

    # Authority of this article, 1.0 = most authoritative, 0.0 = least authoritative
    authority = Column(Float)
    # Time of the last scrape of this article
    scraped = Column(DateTime, index=True)
    # Time of the last parse of this article
    parsed = Column(DateTime, index=True)
    # Time of the last processing of this article
    processed = Column(DateTime, index=True)
    # Time of the last indexing of this article
    indexed = Column(DateTime, index=True)
    # Module used for scraping
    scr_module = Column(String(80))
    # Class within module used for scraping
    scr_class = Column(String(80))
    # Version of scraper class
    scr_version = Column(String(16))
    # Version of parser/grammar/config
    parser_version = Column(String(32))
    # Parse statistics
    num_sentences = Column(Integer)
    num_parsed = Column(Integer)
    ambiguity = Column(Float)

    # The HTML obtained in the last scrape
    html = Column(String)
    # The parse tree obtained in the last parse
    tree = Column(String)
    # The tokens of the article in JSON string format
    tokens = Column(String)
    # The article topic vector as an array of floats in JSON string format
    topic_vector = Column(String)

    # The back-reference to the Root parent of this Article
    root = relationship(
        "Root",
        foreign_keys="Article.root_id",
        backref=backref("articles", order_by=url),
    )

    def __repr__(self):
        return "Article(url='{0}', heading='{1}', scraped={2})".format(
            self.url, self.heading, self.scraped
        )


class Entity(Base):
    """ Represents a named entity """

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
    name = Column(String, index=True)

    @hybrid_property
    def name_lc(self):
        return self.name.lower()

    @name_lc.comparator  # type: ignore
    def name_lc(cls):  # pylint: disable=no-self-argument
        return CaseInsensitiveComparator(cls.name)

    # Verb ('er', 'var', 'sé')
    verb = Column(String, index=True)
    # Entity definition
    definition = Column(String, index=True)

    # Authority of this fact, 1.0 = most authoritative, 0.0 = least authoritative
    authority = Column(Float)

    # Timestamp of this entry
    timestamp = Column(DateTime)

    # The back-reference to the Article parent of this Entity
    article = relationship("Article", backref=backref("entities", order_by=name))

    # Add an index on the entity name in lower case
    name_lc_index = Index('ix_entities_name_lc', func.lower(name))

    def __repr__(self):
        return "Entity(id='{0}', name='{1}', verb='{2}', definition='{3}')".format(
            self.id, self.name, self.verb, self.definition
        )

