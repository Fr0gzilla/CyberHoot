"""Réglages de gunicorn en service."""

import os

bind = "0.0.0.0:8000"
workers = int(os.environ.get("GUNICORN_WORKERS", "3"))
threads = 4
timeout = 30
graceful_timeout = 20
accesslog = "-"
errorlog = "-"
proc_name = "cyberhoot"
forwarded_allow_ips = "*"  # le conteneur n'est joignable que par Nginx (réseau interne)
