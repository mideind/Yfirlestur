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


    API routes
    Note: All routes ending with .api, .task and .process are configured
    not to be cached by nginx

"""

from typing import Any, Dict, Tuple, Optional

import os
import time
import threading
import json
import uuid
from datetime import datetime, timedelta
from functools import partial
import multiprocessing
import multiprocessing.pool
import multiprocessing.managers

from flask import request, abort, url_for, current_app, Request

from settings import Settings

from correct import check_grammar
from doc import SUPPORTED_DOC_MIMETYPES, doc_class_for_mime_type

from . import routes, better_jsonify, text_from_request


# For how long do we keep correction task results around?
RESULT_AVAILABILITY_WINDOW = timedelta(minutes=2)
# How often do we check and clean up old results sitting in memory?
CLEANUP_INTERVAL = 15  # Seconds
# How long do we wait for a child task to complete before aborting
# a synchronous request?
MAX_SYNCHRONOUS_WAIT = 5 * 60.0  # 5 minutes
# How may child processes do we allow to be active at any given point in time?
MAX_CHILD_TASKS = 250
# Multiprocessing context with a 'fork' start method
_CTX = multiprocessing.get_context("fork")
# Number of processes in worker pool
# By default, use all available CPU cores except one
POOL_SIZE = int(os.environ.get("POOL_SIZE", multiprocessing.cpu_count() - 1))


@routes.route("/correct.task", methods=["POST"])
@routes.route("/correct.task/v<int:version>", methods=["POST"])
def correct_async(version: int = 1) -> Any:
    """ Correct text provided by the user, i.e. not coming from an article.
        This can be either an uploaded file or a string. This is a lower level,
        asynchronous API used by the Greynir web front-end. """
    valid, result = validate(request, version)
    if not valid:
        return result
    assert isinstance(result, str)
    # Launch the correction task within a child process
    # and return an intermediate HTTP 202 result including a status/result URL
    # that can be queried later to obtain the progress or the final result
    return ChildTask().launch(result)


@routes.route("/correct.api", methods=["POST"])
@routes.route("/correct.api/v<int:version>", methods=["POST"])
def correct_sync(version: int = 1) -> Any:
    """ Correct text provided by the user, i.e. not coming from an article.
        This can be either an uploaded file or a string.
        This is a synchronous HTTP API call that is easy for third party
        code to work with. """
    valid, result = validate(request, version)
    if not valid:
        return result
    assert isinstance(result, str)
    # Launch the correction task within a child process and wait for its outcome
    task = ChildTask()
    task.launch(result)
    duration = 0.0
    INCREMENT = 1.5  # Seconds
    # Wait for the correction task for a maximum of 5 minutes
    while duration < MAX_SYNCHRONOUS_WAIT:
        # Check the progress of the child task once every 1.5 seconds
        time.sleep(INCREMENT)
        if task.is_complete:
            # Finished (or an exception occurred): return the result
            return task.result()
        duration += INCREMENT
    return better_jsonify(
        valid=False,
        reason=f"Request took too long to process; maximum is "
        f"{MAX_SYNCHRONOUS_WAIT/60.0:.1f} minutes",
    )


def validate(request: Request, version: int) -> Tuple[bool, Any]:
    """ Validate an incoming correction request and extract the
        text to validate from it, if valid """
    if not (1 <= version <= 1):
        return False, better_jsonify(valid=False, reason="Unsupported version")

    file = request.files.get("file")
    if file is not None:

        # Handle uploaded file
        # file is a proxy object that emulates a Werkzeug FileStorage object
        mimetype = file.mimetype
        if mimetype not in SUPPORTED_DOC_MIMETYPES:
            return False, better_jsonify(valid=False, reason="File type not supported")

        # Create document object from an uploaded file and extract its text
        try:
            # Instantiate an appropriate class for the MIME type of the file
            doc_class = doc_class_for_mime_type(mimetype)
            doc = doc_class(file.read())
            text = doc.extract_text()
        except Exception as e:
            current_app.logger.warning("Exception in correct_process(): {0}".format(e))  # type: ignore
            return False, better_jsonify(valid=False, reason="Error reading file")

    else:

        # Handle POSTed form data or plain text string
        try:
            text = text_from_request(request)
        except Exception as e:
            current_app.logger.warning("Exception in correct_process(): {0}".format(e))  # type: ignore
            return False, better_jsonify(valid=False, reason="Invalid request")

    text = text.strip()
    if not text:
        return False, better_jsonify(valid=False, reason="Empty request")

    # Request validated, return the text to correct
    return True, text


class ChildTask:

    """ A container class for the multiprocessing pool logic we use
        to distribute correction workloads between CPU cores """

    processes: Dict[str, "ChildTask"] = dict()
    pool: Optional[multiprocessing.pool.Pool] = None
    manager: Optional[multiprocessing.managers.SyncManager] = None
    lock = threading.Lock()
    progress: Dict[str, float] = dict()

    @classmethod
    def init_pool(cls) -> None:
        """ If needed, create the multiprocessing pool we'll use
            for concurrent processing of correction tasks """
        with cls.lock:
            if cls.pool is None:
                # Set up a Manager for shared memory messaging
                cls.manager = _CTX.Manager()
                # Create an inter-process dict object to hold progress info
                assert cls.manager is not None
                cls.progress = cls.manager.dict()
                # Initialize the worker process pool
                cls.pool = _CTX.Pool(POOL_SIZE)

    def __init__(self) -> None:
        # Create the process pool that will be used for correction tasks.
        # We do this as late as possible, upon invocation of the first ChildTask.
        # Note that ChildTask instances are never created in child processes.
        self.init_pool()
        # Create a new, unique (random) process identifier
        self.identifier = uuid.uuid4().hex
        self.processes[self.identifier] = self
        # Store the initial progress in the interprocess dict
        self.progress[self.identifier] = 0.0
        # Initialize the process status
        self.status: Optional[multiprocessing.pool.ApplyResult[Tuple[Any, ...]]] = None
        self.task_result: Optional[Tuple[Any, ...]] = None
        self.exception: Optional[BaseException] = None
        self.text = ""
        self.started = datetime.utcnow()

    @staticmethod
    def progress_func(process_id: str, progress: float) -> None:
        """ Update the child task progress in the shared dictionary """
        if process_id in ChildTask.progress:
            ChildTask.progress[process_id] = progress

    @staticmethod
    def task(process_id: str, text: str) -> Tuple[Any, ...]:
        """ This is a task that runs in a child process within the pool """
        # We do a bit of functools.partial magic to pass the process_id as the first
        # parameter to the progress_func whenever it is called
        task_result = check_grammar(
            text,
            progress_func=partial(ChildTask.progress_func, process_id),
            split_paragraphs=False,
        )
        # The result is automatically communicated back to the parent process via IPC
        return task_result

    def complete(self, task_result: Tuple[Any, ...]) -> None:
        """ This runs in the parent process when the task has completed
            within the child process """
        self.task_result = task_result

    def error(self, e: BaseException) -> None:
        """ This runs in the parent process and is called if the
            child task raised an exception """
        self.exception = e

    @property
    def is_complete(self) -> bool:
        """ Return True if the child process has finished this task """
        return self.task_result is not None or self.exception is not None

    @property
    def current_progress(self) -> float:
        """ Return the current progress of this child task """
        return self.progress.get(self.identifier, 0.0)

    def finish(self) -> Tuple[Any, Any, str]:
        """ Finish a task that ran within a child process,
            removing it from the dictionary of active tasks
            and returning its results """
        if self.exception is not None:
            # The child process raised an exception: re-raise it
            # after removing this task from the process dictionary
            self.abort()
            raise self.exception
        if self.task_result is None:
            raise ValueError("Child task is not complete")
        assert self.identifier in self.processes
        pgs, stats = self.task_result
        text = self.text
        self.abort()
        return pgs, stats, text

    def abort(self) -> None:
        """ The child task has finished with an exception:
            remove it from the dictionary of active tasks
            as well as from the progress dictionary """
        try:
            del self.processes[self.identifier]
        except KeyError:
            pass
        try:
            del self.progress[self.identifier]
        except KeyError:
            pass

    def launch(self, text: str) -> Any:
        """ Launch a new task using a child process from the pool,
            correcting the given text """
        assert self.pool is not None
        if len(self.processes) > MAX_CHILD_TASKS:
            # Protect the server by not allowing too many child tasks at the same time
            return (
                json.dumps(
                    dict(valid=False, error="Too many child tasks already running")
                ),
                503,  # SERVER BUSY
            )
        self.text = text
        # Here the magic happens, i.e. the handover into one of the child
        # processes via pickling and interprocess communication
        self.status = self.pool.apply_async(
            ChildTask.task,
            args=(self.identifier, text,),
            callback=self.complete,
            error_callback=self.error,
        )
        # Return a HTTP 202 status, including a status-checking URL
        return (
            json.dumps(dict(progress=0.0)),
            202,  # ACCEPTED
            {
                "Location": url_for(
                    "routes.get_process_status", process=self.identifier
                ),
                "Content-Type": "application/json; charset=utf-8",
            },
        )

    @classmethod
    def get_status(cls, process_id: str) -> Any:
        """ Get the status of an ongoing correction task """
        process = cls.processes.get(process_id)
        if process is None:
            # This is not an ongoing task
            abort(410)  # Return HTTP 410 GONE
        return process.result()

    def result(self) -> Any:
        """ Return a Response object with the current status of this child task """
        if self.exception is not None:
            # The task raised an exception: remove it herewith,
            # and return an HTTP 200 reply with an error message
            self.abort()
            return better_jsonify(valid=False, error=str(self.exception))
        if self.task_result is not None:
            # Task completed: return a HTTP 200 reply with a success result
            pgs, stats, text = self.finish()
            return better_jsonify(valid=True, result=pgs, stats=stats, text=text)
        # Not yet completed: report progress
        return (
            json.dumps(dict(progress=self.current_progress)),
            202,  # ACCEPTED
            {
                "Location": url_for(
                    "routes.get_process_status", process=self.identifier
                ),
                "Content-Type": "application/json; charset=utf-8",
            },
        )

    @classmethod
    def cleanup(cls) -> None:
        """ Clean up lapsed child tasks from the processes dict.
            This is called every 15 seconds from a housecleaner thread. """
        # Only keep tasks that are running or
        # that finished within the result availability window
        keep_results = datetime.utcnow() - RESULT_AVAILABILITY_WINDOW
        with cls.lock:
            # Create a list of completed processes that are older than the limit
            lapsed = [
                process.identifier
                for process in cls.processes.values()
                if process.started < keep_results and process.task_result is not None
            ]
            # Delete the lapsed processes from our list
            for process_id in lapsed:
                del cls.processes[process_id]
                del cls.progress[process_id]


@routes.route("/status/<process>", methods=["GET"])
def get_process_status(process: str):
    """ Return the status of a correction task. If this request returns a
        202 ACCEPTED status code, it means that the task hasn't finished yet.
        Else, the result from the task is returned (normally with a 200 OK status). """
    return ChildTask.get_status(process)


@routes.before_app_first_request  # type: ignore
def delete_old_child_tasks() -> None:
    """ Start a background thread that cleans up old tasks """

    def delete_tasks() -> None:
        """ This function runs every 15 seconds and initiates a clean-up
            of completed child tasks """
        while True:
            time.sleep(CLEANUP_INTERVAL)
            ChildTask.cleanup()

    # Don't start the cleanup thread if we're only running tests
    if not current_app.config["TESTING"]:
        thread = threading.Thread(target=delete_tasks)
        thread.start()


@routes.route("/exit.api", methods=["GET"])
def exit_api():
    """ Allow a server to be remotely terminated if running in debug mode """
    if not Settings.DEBUG:
        abort(404)
    shutdown_func = request.environ.get("werkzeug.server.shutdown")
    if shutdown_func is None:
        abort(404)
    shutdown_func()
    return "The server has shut down"
