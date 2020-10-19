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

from flask import request, abort, url_for, current_app

from settings import Settings

from correct import check_grammar
from doc import SUPPORTED_DOC_MIMETYPES, MIMETYPE_TO_DOC_CLASS

from . import routes, better_jsonify, text_from_request


# For how long do we keep correction task results around?
RESULT_AVAILABILITY_WINDOW = timedelta(minutes=2)
# How often do we check and clean up old results sitting in memory?
CLEANUP_INTERVAL = 15  # Seconds
# How may child processes do we allow to be active at any given point in time?
MAX_CHILD_TASKS = 250
# Multiprocessing context with a 'fork' start method
_CTX = multiprocessing.get_context("fork")
# Number of processes in worker pool
# By default, use all available CPU cores except one
POOL_SIZE = int(os.environ["POOL_SIZE"], multiprocessing.cpu_count() - 1)


@routes.route("/correct.api", methods=["POST"])
@routes.route("/correct.api/v<int:version>", methods=["POST"])
def correct_process(version: int = 1) -> Any:
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
            current_app.logger.warning("Exception in correct_process(): {0}".format(e))
            return better_jsonify(valid=False, reason="Error reading file")

    else:

        # Handle POSTed form data or plain text string
        try:
            text = text_from_request(request)
        except Exception as e:
            current_app.logger.warning("Exception in correct_process(): {0}".format(e))
            return better_jsonify(valid=False, reason="Invalid request")

    # Launch the correction task within a child process
    return ChildTask().launch(text)


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
        self.status: Optional[multiprocessing.pool.ApplyResult] = None
        self.result: Optional[Tuple] = None
        self.exception: Optional[BaseException] = None
        self.text = ""
        self.started = datetime.utcnow()

    @staticmethod
    def progress_func(process_id: str, progress: float) -> None:
        """ Update the child task progress in the shared dictionary """
        if process_id in ChildTask.progress:
            ChildTask.progress[process_id] = progress

    @staticmethod
    def task(process_id: str, text: str) -> Tuple:
        """ This is a task that runs in a child process within the pool """
        # We do a bit of functools.partial magic to pass the process_id as the first
        # parameter to the progress_func whenever it is called
        result = check_grammar(
            text, progress_func=partial(ChildTask.progress_func, process_id)
        )
        # The result is automatically communicated back to the parent process via IPC
        return result

    def complete(self, result: Tuple) -> None:
        """ This runs in the parent process when the task has completed
            within the child process """
        self.result = result

    def error(self, e: BaseException) -> None:
        """ This runs in the parent process and is called if the
            child task raised an exception """
        self.exception = e

    @property
    def is_complete(self) -> bool:
        """ Return True if the child process has finished this task """
        return self.result is not None or self.exception is not None

    @property
    def current_progress(self) -> float:
        """ Return the current progress of this child task """
        return self.progress.get(self.identifier, 0.0)

    def finish(self) -> Tuple:
        """ Finish a task that ran within a child process,
            removing it from the dictionary of active tasks
            and returning its results """
        if self.exception is not None:
            # The child process raised an exception: re-raise it
            # after removing this task from the process dictionary
            self.abort()
            raise self.exception
        if self.result is None:
            raise ValueError("Child task is not complete")
        assert self.identifier in self.processes
        pgs, stats = self.result
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
        if process.exception is not None:
            # The task raised an exception: remove it herewith,
            # and return an HTTP 200 reply with an error message
            process.abort()
            return better_jsonify(valid=False, error=str(process.exception))
        if process.result is not None:
            # Task completed: return a HTTP 200 reply with a success result
            pgs, stats, text = process.finish()
            return better_jsonify(valid=True, result=pgs, stats=stats, text=text)
        # Not yet completed: report progress
        return (
            json.dumps(dict(progress=process.current_progress)),
            202,  # ACCEPTED
            {
                "Location": url_for("routes.get_process_status", process=process_id),
                "Content-Type": "application/json; charset=utf-8",
            },
        )

    @classmethod
    def cleanup(cls) -> None:
        # Only keep tasks that are running or
        # that finished within the result availability window
        keep_results = datetime.utcnow() - RESULT_AVAILABILITY_WINDOW
        with cls.lock:
            # Create a list of completed processes that are older than the limit
            lapsed = [
                process.identifier
                for process in cls.processes.values()
                if process.started < keep_results and process.result is not None
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


@routes.before_app_first_request
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
        raise RuntimeError("Not running with the Werkzeug Server")
    shutdown_func()
    return "The server has shut down"
