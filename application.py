import os
from flask import Flask, request
import requests
from queue import Queue
from threading import Event, Lock, Thread
from time import time
from datetime import datetime, timedelta
from skyfield.api import Loader, Topos
from skyfield import almanac
import numpy as np


application = Flask(__name__)

WEBHOOKS_HOST = 'maker.ifttt.com'
WEBHOOKS_KEY = os.environ['WEBHOOKS_KEY']

LIGHT_DURATION = 300

def webhooks_trigger(event):
    application.logger.debug(f"Webhooks trigger {event}")
    r = requests.get(f"https://{WEBHOOKS_HOST}/trigger/{event}/with/key/{WEBHOOKS_KEY}")
    r.raise_for_status()

@application.route("/")
def hello():
    return {"Hello": "World!"}

class Lights:
    def __init__(self):
        self._lock = Lock()
        self._on = True # Assume on
        self.on = False
    
    @property
    def on(self):
        with self._lock:
            return self._on

    @on.setter
    def on(self, on):
        with self._lock:
            if on and not self._on:
                self._on = True
                webhooks_trigger('outdoor_lights_on')
            elif not on and self._on:
                self._on = False
                webhooks_trigger('outdoor_lights_off')
    

class Sun:
    """
    >>> sun = Sun(('59.499505 N', '18.085150 E'))
    >>> t = lambda *date: sun._ts.utc(datetime(*date).astimezone())
    >>> sun._sun_up(t(2019, 7, 8, 22, 0))
    True
    >>> sun._sun_up(t(2019, 7, 8, 22, 1))
    False
    >>> sun._sun_up(t(2019, 7, 9, 3, 45))
    False
    >>> sun._sun_up(t(2019, 7, 9, 3, 46))
    True
    >>> up = sun.up
    """
    def __init__(self, location):
        load = Loader('~/skyfield-data')
        self._ts = load.timescale()
        planets = load('de421.bsp')
        loc = Topos(*location)
        self._sun_up = almanac.sunrise_sunset(planets, loc)

    @property
    def up(self):
        return self._sun_up(self._ts.now())

class TimeSlot:
    """ Defines a time slot 
    >>> awake = TimeSlot('06:00', '23:00', {0, 1, 2, 3, 4})
    >>> t0 = datetime.fromisoformat('2019-07-08 00:00')
    >>> h = timedelta(hours=1)
    >>> for i in range(24):
    ...     t = t0 + i * h
    ...     print(f"{t}: {awake.within(t)}")
    2019-07-08 00:00:00: False
    2019-07-08 01:00:00: False
    2019-07-08 02:00:00: False
    2019-07-08 03:00:00: False
    2019-07-08 04:00:00: False
    2019-07-08 05:00:00: False
    2019-07-08 06:00:00: True
    2019-07-08 07:00:00: True
    2019-07-08 08:00:00: True
    2019-07-08 09:00:00: True
    2019-07-08 10:00:00: True
    2019-07-08 11:00:00: True
    2019-07-08 12:00:00: True
    2019-07-08 13:00:00: True
    2019-07-08 14:00:00: True
    2019-07-08 15:00:00: True
    2019-07-08 16:00:00: True
    2019-07-08 17:00:00: True
    2019-07-08 18:00:00: True
    2019-07-08 19:00:00: True
    2019-07-08 20:00:00: True
    2019-07-08 21:00:00: True
    2019-07-08 22:00:00: True
    2019-07-08 23:00:00: False
    >>> awake.within(t0 + timedelta(days=4, hours=10))
    True
    >>> awake.within(t0 + timedelta(days=5, hours=10))
    False
    >>> active = awake.active
    """
    def __init__(self, start, stop, weekdays=None):
        self._range = np.array([datetime.strptime(t, "%H:%M") for t in [start, stop]])
        self._weekdays = weekdays

    def within(self, x):
        if self._weekdays is not None and x.weekday() not in self._weekdays:
            return False
        until_next = self._range - x - timedelta(microseconds=1)
        return until_next[0].seconds > until_next[1].seconds

    @property
    def active(self):
        return self.within(datetime.today())


class Scheduler(Thread):
    def __init__(self, sun, on_slots):
        super().__init__()
        self._dirty = Event()
        self._lights = Lights()
        self._sun = sun
        self._on_slots = on_slots
        self._greet_until = None

    def run(self):
        while True:
            try:
                self._loop()
                self._dirty.wait(1.0)
                self._dirty.clear()
            except BaseException as e:
                application.logger.error(f"Scheduler: {repr(e)}")

    def _loop(self):
        on = False
        for on_slot in self._on_slots:
            if on_slot.active:
                application.logger.debug(f"on slot active")
                on = True
        if self._greet_until is not None and datetime.today() < self._greet_until:
            application.logger.debug(f"{datetime.today()} < {self._greet_until}")
            on = True
        if self._sun.up:
            application.logger.debug(f"Sun up")
            on = False
        self._lights.on = on


    def greet(self, duration: timedelta):
        self._greet_until = datetime.today() + duration
        self._dirty.set()


LOCATION = os.environ['LOCATION'].split(':')
scheduler = Scheduler(Sun(LOCATION), {TimeSlot('06:00', '23:00')})
scheduler.start()

@application.route("/webhooks/arlo/<event>/<device>")
def webhooks_arlo(event, device):
    scheduler.greet(timedelta(minutes=5))
    return ""


loopback_complete = Queue()
@application.route("/trigger_loopback")
def trigger_loopback():
    application.logger.info(f"trigger_loopback: {request}:{request.args}")
    start = time()
    r = requests.get(trigger_url('loopback'), json={f'value{i}': request.args.get(f'value{i}', i) for i in [1, 2, 3]})
    application.logger.info(f"{r}, {r.text}")
    r.raise_for_status()
    response = loopback_complete.get(timeout=10.0)
    response['round trip'] = time() - start
    return response

@application.route("/loopback")
def loopback():
    application.logger.info(f"loopback: {request.json}")
    loopback_complete.put(request.json)
    return ""
