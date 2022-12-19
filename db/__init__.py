"""

    Yfirlestur: Online spelling and grammar correction for Icelandic

    Copyright (C) 2022 Miðeind ehf.

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


    This module contains database-related functionality.

"""

from typing import Optional, Callable, Any, Type, cast
from typing_extensions import Literal

from sqlalchemy import create_engine, desc, func as dbfunc  # type: ignore
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.engine.cursor import CursorResult  # type: ignore
from sqlalchemy.exc import (
    SQLAlchemyError as DatabaseError,
    IntegrityError,
    DataError,
    OperationalError,
)

from settings import Settings, ConfigError

from .models import Base


class Scraper_DB:

    """Wrapper around the SQLAlchemy connection, engine and session"""

    def __init__(self):
        """Initialize the SQLAlchemy connection to the scraper database"""

        # Assemble the right connection string for CPython/psycopg2 vs.
        # PyPy/psycopg2cffi, respectively
        conn_str = "postgresql+{0}://reynir:reynir@{1}:{2}/scraper".format(
            "psycopg2cffi",  # if is_pypy else "psycopg2",
            Settings.DB_HOSTNAME,
            Settings.DB_PORT,
        )

        # Create engine and bind session
        self._engine = create_engine(conn_str)
        self._Session: Type[Session] = cast(
            Type[Session], sessionmaker(bind=self._engine)
        )

    def create_tables(self) -> None:
        """Create all missing tables in the database"""
        Base.metadata.create_all(self._engine)  # type: ignore

    def execute(self, sql: str, **kwargs: Any) -> CursorResult:
        """Execute raw SQL directly on the engine"""
        return self._engine.execute(sql, **kwargs)  # type: ignore

    @property
    def session(self) -> Session:
        """Returns a freshly created Session instance from the sessionmaker"""
        return self._Session()


class classproperty:

    """Shim to create a property on a class"""

    def __init__(self, f: Callable[..., Any]) -> None:
        self.f = f

    def __get__(self, obj: Any, owner: Any) -> Any:
        return self.f(owner)


class SessionContext:

    """Context manager for database sessions"""

    # Singleton instance of Scraper_DB
    _db: Optional[Scraper_DB] = None

    # pylint: disable=no-self-argument
    @classproperty
    def db(cls) -> Scraper_DB:
        if cls._db is None:
            cls._db = Scraper_DB()
        return cls._db

    @classmethod
    def cleanup(cls) -> None:
        """Clean up the reference to the singleton Scraper_DB instance"""
        cls._db = None

    def __init__(
        self,
        session: Optional[Session] = None,
        commit: bool = False,
        read_only: bool = False,
    ) -> None:

        if session is None:
            # Create a new session that will be automatically committed
            # (if commit == True) and closed upon exit from the context
            # pylint: disable=no-member
            # Creates a new Scraper_DB instance if needed
            self._session = self.db.session
            self._new_session = True
            if read_only:
                # Set the transaction as read only, which can save resources
                self._session.execute("SET TRANSACTION READ ONLY")
                self._commit = True
            else:
                self._commit = commit
        else:
            self._new_session = False
            self._session = session
            self._commit = False

    def __enter__(self) -> Session:
        """Python context manager protocol"""
        # Return the wrapped database session
        return self._session

    # noinspection PyUnusedLocal
    def __exit__(
        self, exc_type: Type[BaseException], exc_value: BaseException, traceback: Any
    ) -> Literal[False]:
        """Python context manager protocol"""
        if self._new_session:
            if self._commit:
                if exc_type is None:
                    # No exception: commit if requested
                    self._session.commit()  # type: ignore
                else:
                    self._session.rollback()  # type: ignore
            self._session.close()  # type: ignore
        # Return False to re-throw exception from the context, if any
        return False


__all__ = (
    "create_engine",
    "desc",
    "dbfunc",
    "sessionmaker",
    "Session",
    "DatabaseError",
    "IntegrityError",
    "DataError",
    "OperationalError",
    "Settings",
    "ConfigError",
    "Scraper_DB",
    "classproperty",
    "SessionContext",
)
