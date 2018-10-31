# -*- coding: utf-8 -*-
import datetime
from glob import glob
import os
from configparser import ConfigParser

from filelock import FileLock

from fakturace.invoices import Invoice, Quote
from fakturace.utils import cached_property


class InvoiceStorage:
    data = "data"
    pdf = "pdf"
    tex = "tex"
    config = "config"
    contacts = "contacts"

    template = "{year}{month}{order}.ini"
    order = "{:02d}"

    base = Invoice

    def __init__(self, basedir="."):
        self.basedir = basedir
        self.lock = FileLock(self.path(self.config, "lock"))

    def path(self, *args):
        return os.path.join(self.basedir, *args)

    def glob(self, year=None, month=None):
        if year:
            year = "{:02d}".format(year % 2000)
        else:
            year = "[0-9][0-9]"
        if month:
            month = "{:02d}".format(month)
        else:
            month = "[0-9][0-9]"
        mask = self.template.format(year=year, month=month, order="*")
        return sorted(glob(self.path(self.data, mask)))

    def list(self, year=None, month=None):
        for filename in self.glob(year, month):
            yield self.base(self, filename)

    def get(self, invoice):
        return self.base(self, self.path(self.data, "{}.ini".format(invoice)))

    @cached_property
    def settings(self):
        data = ConfigParser()
        data.read(self.path(self.config, "config.ini"))
        return dict(data["config"])

    def find_filename(self):
        today = datetime.date.today()
        year = today.strftime("%y")
        month = today.strftime("%m")
        for i in range(1, 1000):
            filename = self.path(
                self.data,
                self.template.format(
                    year=year, month=month, order=self.order.format(i)
                ),
            )
            if os.path.exists(filename):
                continue
            return filename
        raise ValueError("Failed to find invoice number!")

    def create(self, contact, duedelta=30, **kwargs):
        with self.lock:
            today = datetime.date.today()
            due = today + datetime.timedelta(days=duedelta)
            filename = self.find_filename()
            invoice = ConfigParser()
            invoice.add_section("invoice")
            invoice.set("invoice", "contact", contact)
            invoice.set("invoice", "date", today.isoformat())
            invoice.set("invoice", "due", due.isoformat())
            # Apply defaults from contact
            contact = self.read_contact(contact)
            for key, value in contact.items():
                if not key.startswith("default_"):
                    continue
                invoice.set("invoice", key[8:], value)
            # Apply passed value
            for key, value in kwargs.items():
                invoice.set("invoice", key, value)
            # Ensure rate and item are present
            for key in ("rate", "item"):
                if not invoice.has_option("invoice", key):
                    invoice.set("invoice", key, "")
            # Store the file
            with open(filename, "w") as handle:
                invoice.write(handle)
            return filename

    def read_contact(self, name):
        data = ConfigParser()
        data.read(self.path(self.contacts, "{0}.ini".format(name)))
        return dict(data["contact"])


class QuoteStorage(InvoiceStorage):
    data = "quotes"
    pdf = "quotes"
    tex = "quotes"

    base = Quote


class WebStorage(InvoiceStorage):
    template = "W{year}{month}{order}.ini"
    order = "{:03d}"
