"""

    Greynir: Natural language processing for Icelandic

    Copyright (C) 2020 Miðeind ehf.

       This program is free software: you can redistribute it and/or modify
       it under the terms of the GNU General Public License as published by
       the Free Software Foundation, either version 3 of the License, or
       (at your option) any later version.
       This program is distributed in the hope that it will be useful,
       but WITHOUT ANY WARRANTY; without even the implied warranty of
       MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
       GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with this program.  If not, see http://www.gnu.org/licenses/.


    This module contains the main Flask routes for the Yfirlestur.is
    web server.

"""

import platform
import sys

from flask import render_template, request, redirect

import reynir

from doc import SUPPORTED_DOC_MIMETYPES

from . import routes, max_age, text_from_request


@routes.route("/", methods=["GET"])
@routes.route("/correct", methods=["GET", "POST"])
def correct():
    """ Handler for a page for spelling and grammar correction
        of user-entered text """
    try:
        txt = text_from_request(request, post_field="txt", get_field="txt")
    except:
        txt = ""
    return render_template(
        "correct.html",
        default_text=txt,
        supported_mime_types=list(SUPPORTED_DOC_MIMETYPES),
    )


@routes.route("/about")
@max_age(seconds=10 * 60)
def about():
    """ Handler for the 'About' page """
    try:
        reynir_version = reynir.__version__
        python_version = "{0} ({1})".format(
            ".".join(str(n) for n in sys.version_info[:3]),
            platform.python_implementation(),
        )
    except AttributeError:
        reynir_version = ""
        python_version = ""
    return render_template(
        "about.html", reynir_version=reynir_version, python_version=python_version
    )
