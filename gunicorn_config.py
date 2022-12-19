# Gunicorn configuration file for yfirlestur.is

# Use same Python hash seed in all child processes
import os

os.environ["PYTHONHASHSEED"] = "31743"

Y_DEBUGGING = os.environ.get("DEBUG", "") in (
    "1",
    "True",
    "TRUE",
    "true",
    "Yes",
    "yes",
    "YES",
)
DEBUG_BIND_IP = os.environ.get("DEBUG_BIND_IP", "127.0.0.1")

if Y_DEBUGGING:
    DIR = "./"
    bind = f"{DEBUG_BIND_IP}:5002"
else:
    DIR = "/usr/share/nginx/yfirlestur.is/"  # type: ignore
    bind = "unix:" + DIR + "gunicorn.sock"

# Since Yfirlestur implements its own multiprocessing pool
# for time-consuming tasks, we don't need a fancy monkey-patching
# worker class such as eventlet.
worker_class = "sync"
workers = 1
threads = 4
timeout = 30

# Read user and group name from text config file
with open(DIR + "gunicorn_user.txt") as f:
    user = f.readline().strip()
    group = f.readline().strip()

pidfile = DIR + "gunicorn.pid"
