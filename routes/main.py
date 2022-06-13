"""

    Greynir: Natural language processing for Icelandic

    Copyright (C) 2021 Miðeind ehf.

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


    This module contains the main Flask routes for the Yfirlestur.is
    web application.

"""

from typing import Any, cast

import platform
import sys

from flask import render_template, request

import reynir_correct

from doc import SUPPORTED_DOC_MIMETYPES

from . import routes, text_from_request


@routes.route("/", methods=["GET"])
@routes.route("/correct", methods=["GET", "POST"])
def correct():
    """Handler for a page for spelling and grammar correction
    of user-entered text"""
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
# @max_age(seconds=10 * 60)
def about():
    """Handler for the 'About' page"""
    try:
        reynir_correct_version: str = cast(Any, reynir_correct).__version__
        python_version = "{0} ({1})".format(
            ".".join(str(n) for n in sys.version_info[:3]),
            platform.python_implementation(),
        )
    except AttributeError:
        reynir_correct_version = ""
        python_version = ""
    return render_template(
        "about.html",
        reynir_correct_version=reynir_correct_version,
        python_version=python_version,
    )
