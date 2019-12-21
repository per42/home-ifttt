# home-ifttt
Connect various IFTTT events related to my house

## Run locally
Create Python 3 venv, with numpy in system site packages:

> python3 -m venv --system-site-packages .venv

Activate it:

> . .venv/bin/activate

Install application requirements:

> pip install -r requirements.txt

Run:

> FLASK_APP=application.py WEBHOOKS_KEY=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx LOCATION="xx.xxxxxx N:xx.xxxxxx E" python -m flask run
