@echo off
set FLASK_APP=app
set FLASK_DEBUG=1
echo Starting Flask application...
python -m flask run --debug
pause