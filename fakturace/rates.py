import json
import os
from decimal import Decimal
from typing import ClassVar
from urllib.request import urlopen

from fakturace.data import CACHE_DIR, RATE_URL


class DecimalEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, Decimal):
            return str(o)
        return super().default(o)


class DecimalRates:
    datacache: ClassVar[dict[str, float]] = {}

    @classmethod
    def download(cls, date: str):
        if not os.path.exists(CACHE_DIR):
            os.makedirs(CACHE_DIR)
        cache_file = os.path.join(CACHE_DIR, f"rates-{date}")

        # Filesystem cache
        if date not in cls.datacache and os.path.exists(cache_file):
            with open(cache_file) as handle:
                # Convert str (from DecimalEncoder) or float (legacy cache) to Decimal
                cls.datacache[date] = {
                    key: Decimal(value) for key, value in json.load(handle).items()
                }

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
                cls.datacache[date][parts[3]] = Decimal(parts[4].replace(",", "."))

            # Update filesystem cache
            with open(cache_file, "w") as handle:
                json.dump(cls.datacache[date], handle, cls=DecimalEncoder)

        return cls.datacache[date]

    @classmethod
    def get(cls, date: str, currency: str):
        if currency == "CZK":
            return 1
        rates = cls.download(date)
        return rates[currency]


class Rates:
    @classmethod
    def get(cls, date: str, currency: str) -> float:
        return float(DecimalRates.get(date, currency))
