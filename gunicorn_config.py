# Gunicorn configuration file for yfirlestur.is

DIR = '/usr/share/nginx/yfirlestur.is/'
#DIR = './'

bind = 'unix:' + DIR + 'gunicorn.sock'
#bind="127.0.0.1:5002"

# Since Yfirlestur implements its own multiprocessing pool
# for time-consuming tasks, we don't need a fancy monkey-patching
# worker class such as eventlet.
worker_class = 'sync'
workers = 1
threads = 4
timeout = 30

# Read user and group name from text config file
with open(DIR + 'gunicorn_user.txt') as f:
    user = f.readline().strip()
    group = f.readline().strip()

pidfile = DIR + 'gunicorn.pid'
