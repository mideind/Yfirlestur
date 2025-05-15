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


    This module contains the main routes for the Yfirlestur.is web application.

"""


import platform
import sys

from flask import render_template, request

from reynir import __version__ as greynir_version
from reynir_correct import __version__ as greynir_correct_version
from tokenizer import __version__ as tokenizer_version

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
        python_version = "{0} ({1})".format(
            ".".join(str(n) for n in sys.version_info[:3]),
            platform.python_implementation(),
        )
        platform_name = platform.system()
    except AttributeError:
        python_version = ""
        platform_name = ""
    return render_template(
        "about.html",
        greynir_correct_version=greynir_correct_version,
        greynir_version=greynir_version,
        tokenizer_version=tokenizer_version,
        python_version=python_version,
        platform_name=platform_name,
    )
