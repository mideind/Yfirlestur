#!/usr/bin/env python
"""

    Greynir: Natural language processing for Icelandic

    Yfirlestur.is server main module

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


    This module is written in Python 3 and is compatible with PyPy3.

    This is the main module of the Yfirlestur.is web server. It uses Flask
    as its web server and templating engine. In production, this module is
    typically run inside Gunicorn (using servlets) under nginx or a
    compatible WSGi HTTP(S) server. For development, it can be run
    directly from the command line and accessed through port 5001.

    Flask routes are imported from routes/*

"""

from typing import List, Pattern, Dict, Any, Optional, Union

import sys
import os
import time
import re
import logging
from datetime import datetime

from flask import Flask, render_template, send_from_directory, jsonify
from flask_caching import Cache  # type: ignore
from flask_cors import CORS  # type: ignore

from werkzeug.middleware.proxy_fix import ProxyFix

import reynir
from reynir.bindb import BIN_Db
from reynir.fastparser import Fast_Parser

import reynir_correct

from settings import Settings, ConfigError


# RUNNING_AS_SERVER is True if we're executing under nginx/Gunicorn,
# but False if the program was invoked directly as a Python main module.
RUNNING_AS_SERVER = __name__ != "__main__"

# Initialize and configure Flask app
app = Flask(__name__)

# Enable Cross Origin Resource Sharing for app
cors = CORS(app)
app.config["CORS_HEADERS"] = "Content-Type"

# Fix access to client remote_addr when running behind proxy
setattr(app, "wsgi_app", ProxyFix(app.wsgi_app))

app.config["JSON_AS_ASCII"] = False  # We're fine with using Unicode/UTF-8
app.config["MAX_CONTENT_LENGTH"] = 1 * 1024 * 1024  # 1 MB, max upload file size
app.config["CACHE_NO_NULL_WARNING"] = True  # Don't warn if caching is disabled

# Only auto-reload templates if we're not running as a production server
app.config["TEMPLATES_AUTO_RELOAD"] = not RUNNING_AS_SERVER

# Push application context to give view functions, error handlers,
# and other functions access to app instance via current_app
app.app_context().push()

# Set up caching
# Caching is disabled if app is invoked via the command line
cache_type = "simple" if RUNNING_AS_SERVER else "null"
cache = Cache(app, config={"CACHE_TYPE": cache_type})
app.config["CACHE"] = cache

# Register blueprint routes
from routes import routes, max_age

app.register_blueprint(routes)


# Utilities for Flask/Jinja2 formatting of numbers using the Icelandic locale
def make_pattern(rep_dict: Dict[str, Any]) -> Pattern:
    return re.compile("|".join([re.escape(k) for k in rep_dict.keys()]), re.M)


def multiple_replace(string: str, rep_dict: Dict[str, str], pattern: Optional[Pattern]=None) -> str:
    """ Perform multiple simultaneous replacements within string """
    if pattern is None:
        pattern = make_pattern(rep_dict)
    return pattern.sub(lambda x: rep_dict[x.group(0)], string)


_REP_DICT_IS = {",": ".", ".": ","}
_PATTERN_IS = make_pattern(_REP_DICT_IS)


@app.template_filter("format_is")
def format_is(r: float, decimals: int=0) -> str:
    """ Flask/Jinja2 template filter to format a number for the Icelandic locale """
    fmt = "{0:,." + str(decimals) + "f}"
    return multiple_replace(fmt.format(float(r)), _REP_DICT_IS, _PATTERN_IS)


@app.template_filter("format_ts")
def format_ts(ts: datetime) -> str:
    """ Flask/Jinja2 template filter to format a timestamp """
    return str(ts)[0:19]


# Flask cache busting for static .css and .js files
@app.url_defaults
def hashed_url_for_static_file(endpoint: str, values: Dict[str, Union[int, str]]) -> None:
    """ Add a ?h=XXX parameter to URLs for static .js and .css files,
        where XXX is calculated from the file timestamp """

    def static_file_hash(filename: str) -> int:
        """ Obtain a timestamp for the given file """
        return int(os.stat(filename).st_mtime)

    if "static" == endpoint or endpoint.endswith(".static"):
        filename = values.get("filename")
        if isinstance(filename, str) and filename.endswith((".js", ".css")):
            # if "." in endpoint:  # has higher priority
            #     blueprint = endpoint.rsplit(".", 1)[0]
            # else:
            #     blueprint = request.blueprint  # can be None too

            # if blueprint:
            #     static_folder = app.blueprints[blueprint].static_folder
            # else:
            static_folder = app.static_folder or ""

            param_name = "h"
            while param_name in values:
                param_name = "_" + param_name
            values[param_name] = static_file_hash(os.path.join(static_folder, filename))


@app.route("/static/fonts/<path:path>")
@max_age(seconds=24 * 60 * 60)  # Cache font for 24 hours
def send_font(path: str):
    return send_from_directory("static/fonts", path)


# Custom 404 error handler
@app.errorhandler(404)
def page_not_found(e):
    """ Return a custom 404 error """
    return render_template("404.html")


# Custom 500 error handler
@app.errorhandler(500)
def server_error(e):
    """ Return a custom 500 error """
    return render_template("500.html")


@app.errorhandler(410)
def resource_gone(e):
    """ Return a custom 410 GONE error """
    return jsonify(valid=False, error=str(e)), 410


# Initialize the main module
t0 = time.time()
try:
    # Read configuration file
    Settings.read(os.path.join("config", "Yfirlestur.conf"))
except ConfigError as e:
    logging.error("Yfirlestur.is did not start due to a configuration error:\n{0}".format(e))
    sys.exit(1)

if Settings.DEBUG:
    print(
        "\nStarting Yfirlestur.is web app at {6} with debug={0}, "
        "host={1}:{2}, db_host={3}:{4}\n"
        "Python {5}".format(
            Settings.DEBUG,
            Settings.HOST,
            Settings.PORT,
            Settings.DB_HOSTNAME,
            Settings.DB_PORT,
            sys.version,
            datetime.utcnow(),
        )
    )
    # Clobber Settings.DEBUG in ReynirPackage and GreynirCorrect
    reynir.Settings.DEBUG = True
    reynir_correct.Settings.DEBUG = True


if not RUNNING_AS_SERVER:

    if os.environ.get("GREYNIR_ATTACH_PTVSD"):
        # Attach to the VSCode PTVSD debugger, enabling remote debugging via SSH
        # import ptvsd

        # ptvsd.enable_attach()
        # ptvsd.wait_for_attach()  # Blocks execution until debugger is attached
        ptvsd_attached = True
        print("Attached to PTVSD")
    else:
        ptvsd_attached = False

    # Run a default Flask web server for testing if invoked directly as a main program

    # Additional files that should cause a reload of the web server application
    # Note: Greynir.grammar is automatically reloaded if its timestamp changes
    extra_files = [
        "Yfirlestur.conf",
        "GreynirPackage.conf",
        "GreynirCorrect.conf",
        "Verbs.conf",
        "Adjectives.conf",
        "AdjectivePredicates.conf",
        "Prepositions.conf",
        "Prefs.conf",
        "Phrases.conf",
        "Names.conf",
    ]

    dirs = list(
        map(os.path.dirname, [__file__, reynir.__file__, reynir_correct.__file__])
    )  # type: List[str]
    for i, fname in enumerate(extra_files):
        # Look for the extra file in the different package directories
        for directory in dirs:
            path = os.path.join(directory, "config", fname)
            path = os.path.realpath(path)
            if os.path.isfile(path):
                extra_files[i] = path
                break
        else:
            print("Extra file '{0}' not found".format(fname))
    # Add src/reynir/resources/ord.compressed from reynir
    extra_files.append(
        os.path.join(
            os.path.dirname(reynir.__file__),
            "src",
            "reynir",
            "resources",
            "ord.compressed",
        )
    )

    from socket import error as socket_error
    import errno

    try:

        # Suppress information log messages from Werkzeug
        werkzeug_log = logging.getLogger("werkzeug")
        if werkzeug_log:
            werkzeug_log.setLevel(logging.WARNING)

        # Pre-load the correction engine into memory
        reynir_correct.check_single("Þetta er upphitun")

        # Run the Flask web server application
        app.run(
            host=Settings.HOST,
            port=Settings.PORT,
            debug=Settings.DEBUG,
            use_reloader=not ptvsd_attached,
            extra_files=extra_files,
        )

    except socket_error as e:
        if e.errno == errno.EADDRINUSE:  # Address already in use
            logging.error(
                "Another server is already running at host {0}:{1}".format(
                    Settings.HOST, Settings.PORT
                )
            )
            sys.exit(1)
        else:
            raise

    finally:
        BIN_Db.cleanup()

else:
    app.config["PRODUCTION"] = True

    gunicorn_logger = logging.getLogger('gunicorn.error')
    if gunicorn_logger is not None:
        # Running under gunicorn: use gunicorn's logger
        app.logger.handlers = gunicorn_logger.handlers
        app.logger.setLevel(gunicorn_logger.level)  # pylint: disable=no-member

    # Log our startup
    log_version = sys.version.replace("\n", " ")
    log_str = (
        f"Yfirlestur.is server instance starting "
        f"with db_host={Settings.DB_HOSTNAME}:{Settings.DB_PORT} "
        f"on Python {log_version}"
    )
    app.logger.info(log_str)  # pylint: disable=no-member

    # Pre-load the correction engine into memory
    reynir_correct.check_single("Þetta er upphitun")

    app.logger.info("Instance warmed up and ready.")  # pylint: disable=no-member
