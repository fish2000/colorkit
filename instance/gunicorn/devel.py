bind = "127.0.0.1:8000"
pidfile = "/Users/fish/Praxa/colorkit/var/run/gunicorn.pid"

worker_class = 'eventlet'

workers = 6
timeout = 300
max_requests = 333

preload_app = True

