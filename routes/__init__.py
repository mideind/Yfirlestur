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


    This module contains all routes for the Yfirlestur.is Flask web application.
    It also contains a number of utility functions and decorators,
    including @async_task which encapsulates a route in an asynchronous
    wrapper.

"""

from typing import TYPE_CHECKING, Tuple, Dict, Any, Callable, Optional, Union, cast

import threading
import time
import uuid
import json
from functools import wraps
from datetime import datetime, timedelta

from flask import (
    Blueprint,
    make_response,
    current_app,
    abort,
    request,
    url_for,
)
from flask import jsonify  # type: ignore
from flask.wrappers import Request, Response
from flask import _request_ctx_stack  # type: ignore
from flask.ctx import RequestContext
from werkzeug.datastructures import FileStorage
from werkzeug.exceptions import HTTPException, InternalServerError


ProgressFunc = Callable[[float], None]

# Maximum length of incoming GET/POST parameters
_MAX_TEXT_LENGTH = 16384
_MAX_TEXT_LENGTH_VIA_URL = 512

_TRUTHY = frozenset(("true", "1", "yes"))

cache = current_app.config["CACHE"]
routes: Blueprint = Blueprint("routes", __name__)


def max_age(
    seconds: int,
) -> Callable[[Callable[[Any], Any]], Callable[[Any], Response]]:
    """Caching decorator for Flask - augments response
    with a max-age cache header"""

    def decorator(f: Callable[[Any], Any]) -> Callable[[Any], Response]:
        @wraps(f)
        def decorated_function(*args: Any, **kwargs: Any) -> Response:
            resp = f(*args, **kwargs)  # type: ignore
            if not isinstance(resp, Response):
                resp = make_response(resp)
            resp.cache_control.max_age = seconds  # type: ignore
            return resp

        return decorated_function

    return decorator


def restricted(f: Callable[[Any], Response]) -> Callable[[Any], Response]:
    """Decorator to return 403 Forbidden if not running in debug mode"""

    @wraps(f)
    def decorated_function(*args: Any, **kwargs: Any) -> Response:
        if not current_app.config["DEBUG"]:
            return abort(403)
        return f(*args, **kwargs)  # type: ignore

    return decorated_function


def bool_from_request(rq: Request, name: str, default: bool = False) -> bool:
    """Get a boolean from JSON encoded in a request form"""
    b = rq.form.get(name)
    if b is None:
        b = rq.args.get(name)
    if b is None:
        # Not present in the form: return the default
        return default
    return isinstance(b, str) and b.lower() in _TRUTHY


def better_jsonify(**kwargs: Any) -> Response:
    """Ensure that the Content-Type header includes 'charset=utf-8'"""
    resp: Response = jsonify(**kwargs)
    resp.headers["Content-Type"] = "application/json; charset=utf-8"
    return resp


def text_from_request(
    rq: Request, *, post_field: Optional[str] = None, get_field: Optional[str] = None
) -> str:
    """Return text passed in a HTTP request, either using GET or POST.
    When using GET, the default parameter name is 't'. This can
    be overridden using the get_field parameter.
    When using POST, the default form field name is 'text'. This can
    be overridden using the post_field parameter.
    """
    if rq.method == "GET":
        return rq.args.get(get_field or "t", "")[0:_MAX_TEXT_LENGTH_VIA_URL]
    if rq.method != "POST":
        # Unknown/unsupported method
        raise ValueError("Unsupported HTTP method")
    content_type = (rq.content_type or "").split(";")[0]
    charset = rq.mimetype_params.get("charset", "utf-8").lower()
    if content_type == "text/plain":
        # Accept plain text POSTs, UTF-8 encoded by default.
        # Example usage:
        # curl -d @example.txt https://yfirlestur.is/correct.api \
        #     --header "Content-Type: text/plain"
        text = rq.data.decode(charset)  # May throw an exception, which is OK
    elif content_type == "application/json":
        # Accept JSON POSTs, UTF-8 encoded.
        # Example usage:
        # curl -d @example.json https://yfirlestur.is/correct.api \
        #     --header "Content-Type: application/json"
        json: Union[None, str, Dict[str, str]] = cast(Any, rq).get_json(silent=True)
        if json is None or not isinstance(json, dict):
            raise ValueError("Invalid JSON")
        text = json.get(post_field or "text", "")
    else:
        # Also accept 'application/x-www-form-urlencoded' requests:
        # curl -d "text=Í dag er ágætt veður en mikil hálka er á götum." \
        #     https://greynir.is/postag.api
        if charset != "utf-8":
            raise ValueError("Form data must be UTF-8 encoded")
        text = rq.form.get(post_field or "text", "")
    return text[0:_MAX_TEXT_LENGTH]


# The following asynchronous support code is adapted from Miguel Grinberg's
# PyCon 2016 "Flask at Scale" tutorial: https://github.com/miguelgrinberg/flack

# A dictionary of currently living tasks
_tasks: Dict[str, Dict[str, Any]] = dict()
_tasks_lock = threading.Lock()


def fancy_url_for(*args: Any, **kwargs: Any) -> str:
    """url_for() replacement that works even when there is no request context"""
    if "_external" not in kwargs:
        kwargs["_external"] = False
    reqctx: Any = _request_ctx_stack.top  # type: ignore
    if reqctx is None:
        if kwargs["_external"]:
            raise RuntimeError(
                "Cannot generate external URLs without a request context."
            )
        with current_app.test_request_context():
            return url_for(*args, **kwargs)
    return url_for(*args, **kwargs)


def start_task_cleanup_thread() -> None:
    """Start a background thread that cleans up old tasks"""

    def clean_old_tasks() -> None:
        """This function cleans up old tasks from an in-memory data structure"""
        global _tasks
        while True:
            # Only keep tasks that are running or
            # that finished less than 5 minutes ago
            five_min_ago = datetime.utcnow() - timedelta(minutes=5)
            with _tasks_lock:
                _tasks = {
                    task_id: task
                    for task_id, task in _tasks.items()
                    if "t" not in task or task["t"] > five_min_ago
                }
            time.sleep(60)

    # Don't start the cleanup thread if we're only running tests
    if not current_app.config["TESTING"]:
        thread = threading.Thread(target=clean_old_tasks)
        thread.start()


class _FileProxy:

    """A hack that implements an in-memory proxy object for a Werkzeug FileStorage
    instance, enabling it to be passed between threads"""

    def __init__(self, fs: FileStorage):
        # Initialize the file proxy object from a Werkzeug FileStorage instance,
        # cf. https://werkzeug.palletsprojects.com/en/1.0.x/datastructures/#werkzeug.datastructures.FileStorage
        self._mimetype = fs.mimetype
        self._mimetype_params = fs.mimetype_params
        self._content_type = fs.content_type
        # !!! Note: this reads the entire file stream into memory.
        # !!! A fancier method using temporary files could be applied here
        # !!! when and if needed.
        self._bytes = fs.read()

    @property
    def mimetype(self) -> str:
        return self._mimetype

    @property
    def mimetype_params(self) -> Dict[str, str]:
        return self._mimetype_params

    @property
    def content_type(self) -> Optional[str]:
        return self._content_type

    def read(self) -> bytes:
        return self._bytes


class _RequestProxy:

    """A hack to emulate a Flask Request object with a data structure
    that can be passed safely between threads, while retaining
    the ability to read uploaded files and form data"""

    def __init__(self, rq: Request) -> None:
        """Create an instance that walks and quacks sufficiently similarly
        to the Flask Request object in rq"""
        self.method = rq.method
        self.headers: Dict[str, Any] = {k: v for k, v in rq.headers}  # type: ignore
        self.environ = rq.environ
        self.blueprint = rq.blueprint
        self.progress_func: Optional[ProgressFunc] = None
        self.form: Dict[str, Any]
        self.data: bytes
        if rq.method == "POST":
            # Copy POSTed data between requests
            if rq.headers.get("Content-Type") == "text/plain":
                # Text data
                self.data = rq.data
                self.form = dict()
            else:
                # Form data
                self.data = b""
                self.form = rq.form.copy()  # type: ignore
        else:
            # GET request, no data needs to be copied
            self.data = b""
            self.form = dict()
        # Copy URL arguments
        self.args: Dict[str, Any] = rq.args.copy()  # type: ignore
        # Make a copy of the passed-in files, if any, so that they
        # can be accessed and processed offline (after the original
        # request has been completed and temporary files deleted)
        self.files: Dict[str, _FileProxy] = {k: _FileProxy(v) for k, v in rq.files.items()}  # type: ignore

    def set_progress_func(self, progress_func: ProgressFunc) -> None:
        """Set a function to call during processing of asynchronous requests"""
        self.progress_func = progress_func


def async_task(f: Callable[[Any], Response]) -> Callable[[Any], Tuple[Any, ...]]:
    """This decorator transforms a sync route into an asynchronous one
    by running it in a background thread"""

    @wraps(f)
    def wrapped(*args: Any, **kwargs: Any) -> Tuple[Any, ...]:

        # Assign a unique id to each asynchronous task
        task_id = uuid.uuid4().hex

        def progress(ratio: float) -> None:
            """Function to call from the worker task to indicate progress."""
            # ratio is a float from 0.0 (just started) to 1.0 (finished)
            _tasks[task_id]["progress"] = ratio

        def task(app: Any, rq: Request) -> None:
            """Run the decorated route function in a new thread"""
            this_task = _tasks[task_id]
            # Pretty ugly hack, but no better solution is apparent:
            # Create a fresh Flask RequestContext object, wrapping our
            # custom _RequestProxy object that can be safely passed between threads
            with RequestContext(app, rq.environ, request=rq):
                try:
                    # Run the original route function and record
                    # the response (return value)
                    rq.set_progress_func(progress)  # type: ignore
                    this_task["rv"] = f(*args, **kwargs)  # type: ignore
                except HTTPException as e:
                    this_task["rv"] = current_app.handle_http_exception(e)  # type: ignore
                except Exception as e:
                    # The function raised an exception, so we set a 500 error
                    this_task["rv"] = InternalServerError()
                    if current_app.debug:
                        # We want to find out if something happened, so reraise
                        raise
                finally:
                    # We record the time of the response, to help in garbage
                    # collecting old tasks
                    this_task["t"] = datetime.utcnow()

        # Record the task, and then launch it
        with _tasks_lock:
            _tasks[task_id] = dict(progress=0.0)
            # Create our own request proxy object that can be safely
            # passed between threads, keeping the form data and uploaded files
            # intact and available even after the original request has been closed
            rq = _RequestProxy(request)
            new_task = threading.Thread(
                target=task,
                args=(current_app._get_current_object(), rq),  # type: ignore
            )

        new_task.start()

        # After starting the task on a new thread, we return a 202 response,
        # with a link in the 'Location' header that the client can use
        # to obtain task status
        return (
            json.dumps(dict(progress=0.0)),
            202,  # ACCEPTED
            {
                "Location": fancy_url_for("routes.get_task_status", task=task_id),
                "Content-Type": "application/json; charset=utf-8",
            },
        )

    return wrapped


@routes.route("/task_status/<task>", methods=["GET"])
def get_task_status(task: str) -> Tuple[str, int, Dict[str, Any]]:
    """Return the status of an asynchronous task. If this request returns a
    202 ACCEPTED status code, it means that task hasn't finished yet.
    Else, the response from the task is returned (normally with a
    200 OK status)."""
    task_id = task
    with _tasks_lock:
        t = _tasks.get(task_id)
        if t is None:
            abort(404)
        if "rv" in t:
            # Task completed
            return t["rv"]
        # Not completed: report progress
        return (
            json.dumps(dict(progress=t["progress"])),
            202,  # ACCEPTED
            {
                "Location": fancy_url_for("routes.get_task_status", task=task_id),
                "Content-Type": "application/json; charset=utf-8",
            },
        )


# Import routes from other files
if not TYPE_CHECKING:
    from .api import *
    from .main import *
