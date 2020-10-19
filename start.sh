#!/bin/bash
rm gunicorn.pid
PYTHONIOENCODING=utf-8 gunicorn -c gunicorn_config.py main:app
