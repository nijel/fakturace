import datetime
import os
import re
from configparser import ConfigParser
from glob import glob

import jinja2
from django.utils.functional import cached_property
from filelock import FileLock

from .invoices import Invoice, Proforma, Quote

LATEX_SUBS = (
    (re.compile(r"\\"), r"\\textbackslash"),
    (re.compile(r"([{}_#%&$])"), r"\\\1"),
    (re.compile(r"~"), r"\~{}"),
    (re.compile(r"\^"), r"\^{}"),
    (re.compile(r'"'), r"''"),
    (re.compile(r"\.\.\.+"), r"\\ldots"),
)


def escape_tex(value):
    newval = value
    for pattern, replacement in LATEX_SUBS:
        newval = pattern.sub(replacement, newval)
    return newval


class InvoiceStorage:
    data = "data"
    pdf = "pdf"
    tex = "tex"
    config = "config"
    contacts = "contacts"
    banks = "banks"

    template = "{year}{month}{order}.ini"
    order = "{:02d}"

    base = Invoice

    def __init__(self, basedir="."):
        self.basedir = basedir
        lockfile = self.path(self.config, "lock")
        self.ensure_dir(lockfile)
        self.lock = FileLock(lockfile)
        self.jinja = jinja2.Environment(
            block_start_string=r"\BLOCK{",
            block_end_string="}",
            variable_start_string=r"\VAR{",
            variable_end_string="}",
            comment_start_string=r"\#{",
            comment_end_string="}",
            line_statement_prefix="%%",
            line_comment_prefix="%#",
            trim_blocks=True,
            autoescape=False,
            loader=jinja2.FileSystemLoader(os.path.abspath(basedir)),
        )
        self.jinja.filters["escape_tex"] = escape_tex

    @staticmethod
    def ensure_dir(filename):
        dirname = os.path.dirname(filename)
        if not os.path.exists(dirname):
            os.makedirs(dirname)

    def path(self, *args):
        return os.path.join(self.basedir, *args)

    def glob(self, year=None, month=None):
        if year:
            full_year = str(year)
            year = "{:02d}".format(year % 2000)
        else:
            full_year = "[0-9][0-9][0-9][0-9]"
            year = "[0-9][0-9]"
        if month:
            month = "{:02d}".format(month)
        else:
            month = "[0-9][0-9]"
        mask = self.template.format(
            year=year, month=month, order="*", full_year=full_year
        )
        return sorted(glob(self.path(self.data, mask)))

    def list(self, year=None, month=None):
        for filename in self.glob(year, month):
            yield self.base(self, filename)

    def get(self, invoice):
        if "/" not in invoice:
            return self.base(self, self.path(self.data, "{}.ini".format(invoice)))
        return self.base(self, self.path(invoice))

    @cached_property
    def settings(self):
        data = ConfigParser()
        data.read(self.path(self.config, "config.ini"))
        return dict(data["config"])

    def find_filename(self):
        today = datetime.date.today()
        year = today.strftime("%y")
        full_year = today.strftime("%Y")
        month = today.strftime("%m")
        for i in range(1, 1000):
            filename = self.path(
                self.data,
                self.template.format(
                    year=year,
                    month=month,
                    order=self.order.format(i),
                    full_year=full_year,
                ),
            )
            if os.path.exists(filename):
                continue
            return filename
        raise ValueError("Failed to find invoice number!")

    def create(self, contact, duedelta=15, **kwargs):
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
            self.ensure_dir(filename)
            with open(filename, "w") as handle:
                invoice.write(handle)
            return filename

    def contact_path(self, name):
        return self.path(self.contacts, "{0}.ini".format(name))

    def parse_contact(self, name):
        data = ConfigParser()
        data.read(self.contact_path(name))
        return data

    def read_contact(self, name):
        data = self.parse_contact(name)
        return dict(data["contact"])

    def bank_path(self, name):
        return self.path(self.banks, "{0}.ini".format(name))

    def read_bank(self, name, extra_suffix=None):
        data = ConfigParser()
        data.read(self.bank_path(name))
        if extra_suffix:
            data.read(self.path(self.banks, "{0}-{1}.ini".format(name, extra_suffix)))
        return dict(data["bank"])

    def update_bank(self, name, **kwargs):
        filename = self.bank_path(name)
        self.ensure_dir(filename)
        if os.path.exists(filename):
            bank = ConfigParser()
            bank.read(filename)
        else:
            bank = ConfigParser()

        if not bank.has_section("bank"):
            bank.add_section("bank")

        for name, value in kwargs.items():
            bank.set("bank", name, value)

        with open(filename, "w") as handle:
            bank.write(handle)
        return filename

    def update_contact(
        self,
        key,
        name,
        address,
        city,
        country,
        email,
        tax_reg,
        vat_reg,
        default_currency,
        default_category,
    ):
        filename = self.contact_path(key)
        self.ensure_dir(filename)
        if os.path.exists(filename):
            contact = self.parse_contact(key)
        else:
            contact = ConfigParser()

        if not contact.has_section("contact"):
            contact.add_section("contact")

        contact.set("contact", "name", name)
        contact.set("contact", "address", address)
        contact.set("contact", "city", city)
        contact.set("contact", "country", country)
        contact.set("contact", "email", email)
        contact.set("contact", "tax_reg", tax_reg)
        contact.set("contact", "vat_reg", vat_reg)
        contact.set("contact", "default_currency", default_currency)
        contact.set("contact", "default_category", default_category)

        with open(filename, "w") as handle:
            contact.write(handle)
        return filename


class QuoteStorage(InvoiceStorage):
    data = "quotes"
    pdf = "quotes"
    tex = "quotes"
    template = "Q{full_year}{order}.ini"

    base = Quote


class WebStorage(InvoiceStorage):
    template = "W{year}{month}{order}.ini"
    order = "{:03d}"


class ProformaStorage(InvoiceStorage):
    data = "proforma"
    pdf = "proforma"
    tex = "proforma"
    template = "P{full_year}{order}.ini"
    order = "{:05d}"

    base = Proforma
