# -*- coding: utf-8 -*-
from glob import glob
import os
from configparser import ConfigParser

from fakturace.invoices import Invoice, Quote
from fakturace.utils import cached_property


class InvoiceStorage:
    data = "data"
    pdf = "pdf"
    tex = "tex"
    config = "config"

    base = Invoice

    def __init__(self, basedir="."):
        self.basedir = basedir

    def path(self, *args):
        return os.path.join(self.basedir, *args)

    def glob(self, year=None, month=None):
        if year:
            if year > 2000:
                year = year - 2000
            if month:
                mask = "{:02d}{:02d}*".format(year, month)
            else:
                mask = "{:02d}*".format(year)
        else:
            mask = "*"
        return sorted(glob(self.path(self.data, "{}.ini".format(mask))))

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


class QuoteStorage(InvoiceStorage):
    data = "quotes"
    pdf = "quotes"
    tex = "quotes"

    base = Quote
