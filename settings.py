"""

    Yfirlestur: Online spelling and grammar correction for Icelandic

    Settings module

    Copyright (c) 2022 Miðeind ehf.

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


    This module reads and interprets the Yfirlestur.conf configuration file.
    The file can include other files using the $include directive,
    making it easier to arrange configuration sections into logical
    and manageable pieces.

    Sections are identified like so: [ section_name ]

    Comments start with # signs.

    Sections are interpreted by section handlers.

"""

from typing import List, Iterator, Optional

import os
import codecs
import locale
import threading

from contextlib import contextmanager


# The locale used by default in the changedlocale function
_DEFAULT_LOCALE = ("IS_is", "UTF-8")


class ConfigError(Exception):

    """Exception class for configuration errors"""

    def __init__(self, s: str) -> None:
        super().__init__(self, s)
        self.fname: Optional[str] = None
        self.line: int = 0

    def set_pos(self, fname: str, line: int) -> None:
        """Set file name and line information, if not already set"""
        if not self.fname:
            self.fname = fname
            self.line = line

    def __str__(self) -> str:
        """Return a string representation of this exception"""
        s = Exception.__str__(self)
        if not self.fname:
            return s
        return "File {0}, line {1}: {2}".format(self.fname, self.line, s)


class LineReader:

    """Read lines from a text file, recognizing $include directives"""

    def __init__(
        self, fname: str, outer_fname: Optional[str] = None, outer_line: int = 0
    ) -> None:
        self._fname = fname
        self._line = 0
        self._inner_rdr: Optional["LineReader"] = None
        self._outer_fname = outer_fname
        self._outer_line = outer_line

    def fname(self) -> str:
        return self._fname if self._inner_rdr is None else self._inner_rdr.fname()

    def line(self) -> int:
        return self._line if self._inner_rdr is None else self._inner_rdr.line()

    def lines(self) -> Iterator[str]:
        """Generator yielding lines from a text file"""
        self._line = 0
        try:
            with codecs.open(self._fname, "r", "utf-8") as inp:
                # Read config file line-by-line
                for s in inp:
                    self._line += 1
                    # Check for include directive: $include filename.txt
                    if s.startswith("$") and s.lower().startswith("$include "):
                        iname = s.split(maxsplit=1)[1].strip()
                        # Do some path magic to allow the included path
                        # to be relative to the current file path, or a
                        # fresh (absolute) path by itself
                        head, _ = os.path.split(self._fname)
                        iname = os.path.join(head, iname)
                        rdr = self._inner_rdr = LineReader(
                            iname, self._fname, self._line
                        )
                        for incl_s in rdr.lines():
                            yield incl_s
                        self._inner_rdr = None
                    else:
                        yield s
        except (IOError, OSError):
            if self._outer_fname:
                # This is an include file within an outer config file
                c = ConfigError(
                    "Error while opening or reading include file '{0}'".format(
                        self._fname
                    )
                )
                c.set_pos(self._outer_fname, self._outer_line)
            else:
                # This is an outermost config file
                c = ConfigError(
                    "Error while opening or reading config file '{0}'".format(
                        self._fname
                    )
                )
            raise c


# Magic stuff to change locale context temporarily


@contextmanager
def changedlocale(new_locale: Optional[str] = None, category: str = "LC_COLLATE"):
    """Change locale temporarily within a context (with-statement)"""
    # The new locale parameter should be a tuple, e.g. ('is_IS', 'UTF-8')
    # The category should be a string such as 'LC_TIME', 'LC_NUMERIC' etc.
    cat = getattr(locale, category)
    old_locale = locale.getlocale(cat)
    try:
        locale.setlocale(cat, new_locale or _DEFAULT_LOCALE)
        yield locale.strxfrm  # Function to transform string for sorting
    finally:
        locale.setlocale(cat, old_locale)


def sort_strings(strings: List[str], loc: Optional[str] = None) -> List[str]:
    """Sort a list of strings using the specified locale's collation order"""
    # Change locale temporarily for the sort
    with changedlocale(loc) as strxfrm:
        return sorted(strings, key=strxfrm)


# Global settings


class Settings:

    _lock = threading.Lock()
    loaded: bool = False

    # Postgres SQL database server hostname and port
    DB_HOSTNAME: str = os.environ.get("GREYNIR_DB_HOST", "localhost")
    db_port_str: str = os.environ.get(
        "GREYNIR_DB_PORT", "5432"
    )  # Default PostgreSQL port

    try:
        DB_PORT = int(db_port_str)
    except ValueError:
        raise ConfigError("Invalid environment variable value: DB_PORT")

    # Flask server host and port
    HOST: str = os.environ.get("GREYNIR_HOST", "localhost")
    port_str: str = os.environ.get("GREYNIR_PORT", "5000")
    try:
        PORT = int(port_str)
    except ValueError:
        raise ConfigError("Invalid environment variable value: GREYNIR_PORT")

    # Flask debug parameter
    DEBUG: bool = False

    # Configuration settings from the Yfirlestur.conf file

    @staticmethod
    def _handle_settings(s: str) -> None:
        """Handle config parameters in the settings section"""
        a = s.lower().split("=", maxsplit=1)
        par = a[0].strip().lower()
        val = a[1].strip()
        try:
            if par == "db_hostname":
                Settings.DB_HOSTNAME = val
            elif par == "db_port":
                Settings.DB_PORT = int(val)
            elif par == "host":
                Settings.HOST = val
            elif par == "port":
                Settings.PORT = int(val)
            elif par == "debug":
                Settings.DEBUG = val.lower() in {"true", "yes", "1"}
            else:
                raise ConfigError("Unknown configuration parameter '{0}'".format(par))
        except ValueError:
            raise ConfigError("Invalid parameter value: {0}={1}".format(par, val))

    @staticmethod
    def read(fname: str) -> None:
        """Read configuration file"""

        with Settings._lock:

            if Settings.loaded:
                return

            CONFIG_HANDLERS = {
                "settings": Settings._handle_settings,
            }
            handler = None  # Current section handler

            rdr = None
            s: str
            try:
                rdr = LineReader(fname)
                for s in rdr.lines():
                    # Ignore comments
                    ix = s.find("#")
                    if ix >= 0:
                        s = s[0:ix]
                    s = s.strip()
                    if not s:
                        # Blank line: ignore
                        continue
                    if s[0] == "[" and s[-1] == "]":
                        # New section
                        section = s[1:-1].strip().lower()
                        if section in CONFIG_HANDLERS:
                            handler = CONFIG_HANDLERS[section]
                            continue
                        raise ConfigError("Unknown section name '{0}'".format(section))
                    if handler is None:
                        raise ConfigError("No handler for config line '{0}'".format(s))
                    # Call the correct handler depending on the section
                    try:
                        handler(s)
                    except ConfigError as e:
                        # Add file name and line number information to the exception
                        # if it's not already there
                        e.set_pos(rdr.fname(), rdr.line())
                        raise e

            except ConfigError as e:
                # Add file name and line number information to the exception
                # if it's not already there
                if rdr:
                    e.set_pos(rdr.fname(), rdr.line())
                raise e

            Settings.loaded = True
