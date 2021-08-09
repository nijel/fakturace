import json
import os
from urllib.request import urlopen

from fakturace.data import CACHE_DIR, RATE_URL


class Rates:
    datacache = {}

    @classmethod
    def download(cls, date):
        if not os.path.exists(CACHE_DIR):
            os.makedirs(CACHE_DIR)
        cache_file = os.path.join(CACHE_DIR, "rates-{0}".format(date))

        # Filesystem cache
        if date not in cls.datacache and os.path.exists(cache_file):
            with open(cache_file, "r") as handle:
                cls.datacache[date] = json.load(handle)

        # Load remotely
        if date not in cls.datacache:
            cls.datacache[date] = {}
            parts = date.split("-")
            handle = urlopen(RATE_URL.format(*parts))
            content = handle.read().decode("utf-8")
            for line in content.splitlines():
                if "|" not in line:
                    continue
                parts = line.split("|")
                if parts[4] in ("kurz", "Rate"):
                    continue
                cls.datacache[date][parts[3]] = float(parts[4].replace(",", "."))

            # Update filesystem cache
            with open(cache_file, "w") as handle:
                json.dump(cls.datacache[date], handle)

        return cls.datacache[date]

    @classmethod
    def get(cls, date, currency):
        if currency == "CZK":
            return 1
        rates = cls.download(date)
        return rates[currency]
