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


    API routes
    Note: All routes ending with .api are configured not to be cached by nginx

"""


from datetime import datetime
import logging

from flask import request, abort

from settings import Settings

from correct import check_grammar
from reynir.binparser import canonicalize_token
from doc import SUPPORTED_DOC_MIMETYPES, MIMETYPE_TO_DOC_CLASS


from . import routes, better_jsonify, text_from_request, bool_from_request, restricted
from . import async_task


@routes.route("/correct.api", methods=["GET", "POST"])
@routes.route("/correct.api/v<int:version>", methods=["GET", "POST"])
def correct_api(version=1):
    """ Correct text provided by the user, i.e. not coming from an article.
        This can be either an uploaded file or a string.
        This is a lower level API used by the Greynir web front-end. """
    if not (1 <= version <= 1):
        return better_jsonify(valid=False, reason="Unsupported version")

    file = request.files.get("file")
    if file is not None:

        # file is a Werkzeug FileStorage object
        mimetype = file.content_type
        if mimetype not in SUPPORTED_DOC_MIMETYPES:
            return better_jsonify(valid=False, reason="File type not supported")

        # Create document object from file and extract text
        try:
            # Instantiate appropriate class for mime type from file data
            # filename = werkzeug.secure_filename(file.filename)
            doc_class = MIMETYPE_TO_DOC_CLASS[mimetype]
            doc = doc_class(file.read())
            text = doc.extract_text()
        except Exception as e:
            logging.warning("Exception in correct_api(): {0}".format(e))
            return better_jsonify(valid=False, reason="Error reading file")

    else:

        try:
            text = text_from_request(request)
        except Exception as e:
            logging.warning("Exception in correct_api(): {0}".format(e))
            return better_jsonify(valid=False, reason="Invalid request")

    pgs, stats = check_grammar(text)

    # Return the annotated paragraphs/sentences and stats
    # in a JSON structure to the client
    return better_jsonify(valid=True, result=pgs, stats=stats, text=text)


@routes.route("/correct.task", methods=["POST"])
@routes.route("/correct.task/v<int:version>", methods=["POST"])
@async_task  # This means that the function is automatically run on a separate thread
def correct_task(version=1):
    """ Correct text provided by the user, i.e. not coming from an article.
        This can be either an uploaded file or a string.
        This is a lower level API used by the Greynir web front-end. """
    if not (1 <= version <= 1):
        return better_jsonify(valid=False, reason="Unsupported version")

    file = request.files.get("file")
    if file is not None:

        # Handle uploaded file
        # file is a proxy object that emulates a Werkzeug FileStorage object
        mimetype = file.mimetype
        if mimetype not in SUPPORTED_DOC_MIMETYPES:
            return better_jsonify(valid=False, reason="File type not supported")

        # Create document object from an uploaded file and extract its text
        try:
            # Instantiate an appropriate class for the MIME type of the file
            doc_class = MIMETYPE_TO_DOC_CLASS[mimetype]
            doc = doc_class(file.read())
            text = doc.extract_text()
        except Exception as e:
            logging.warning("Exception in correct_task(): {0}".format(e))
            return better_jsonify(valid=False, reason="Error reading file")

    else:

        # Handle POSTed form data or plain text string
        try:
            text = text_from_request(request)
        except Exception as e:
            logging.warning("Exception in correct_task(): {0}".format(e))
            return better_jsonify(valid=False, reason="Invalid request")

    pgs, stats = check_grammar(text, progress_func=request.progress_func)

    # Return the annotated paragraphs/sentences and stats
    # in a JSON structure to the client
    return better_jsonify(valid=True, result=pgs, stats=stats, text=text)


@routes.route("/exit.api", methods=["GET"])
def exit_api():
    """ Allow a server to be remotely terminated if running in debug mode """
    if not Settings.DEBUG:
        abort(404)
    shutdown_func = request.environ.get("werkzeug.server.shutdown")
    if shutdown_func is None:
        raise RuntimeError("Not running with the Werkzeug Server")
    shutdown_func()
    return "The server has shut down"
