from __future__ import annotations

import datetime
import os
import re
from configparser import RawConfigParser
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

DASH_RE = re.compile(r"-")


def escape_tex(value):
    newval = value
    for pattern, replacement in LATEX_SUBS:
        newval = pattern.sub(replacement, newval)
    return newval


def escape_dash(value):
    return DASH_RE.sub(r"--", value)


class InvoiceStorage:
    data = "data"
    pdf = "pdf"
    tex = "tex"
    config = "config"
    contacts = "contacts"
    banks = "banks"
    default_due = 15

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
        self.jinja.filters["escape_dash"] = escape_dash

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
            year = f"{year % 2000:02d}"
        else:
            full_year = "[0-9][0-9][0-9][0-9]"
            year = "[0-9][0-9]"
        month = f"{month:02d}" if month else "[0-9][0-9]"
        mask = self.template.format(
            year=year,
            month=month,
            order="*",
            full_year=full_year,
        )
        return sorted(glob(self.path(self.data, mask)))

    def list(self, year=None, month=None):
        for filename in self.glob(year, month):
            yield self.base(self, filename)

    def get(self, invoice):
        if "/" not in invoice:
            return self.base(self, self.path(self.data, f"{invoice}.ini"))
        return self.base(self, self.path(invoice))

    @cached_property
    def settings(self):
        data = RawConfigParser()
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

    def create(self, contact, duedelta: int | None = None, **kwargs):
        if duedelta is None:
            duedelta = self.default_due
        with self.lock:
            today = datetime.date.today()
            due = today + datetime.timedelta(days=duedelta)
            filename = self.find_filename()
            invoice = RawConfigParser()
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
        return self.path(self.contacts, f"{name}.ini")

    def parse_contact(self, name):
        data = RawConfigParser()
        data.read(self.contact_path(name))
        return data

    def read_contact(self, name):
        data = self.parse_contact(name)
        try:
            return dict(data["contact"])
        except KeyError as error:
            raise ValueError(f"Contact {name} not found!") from error

    def bank_path(self, name):
        return self.path(self.banks, f"{name}.ini")

    def read_bank(self, name, extra_suffix=None):
        data = RawConfigParser()
        data.read(self.bank_path(name))
        if extra_suffix:
            data.read(self.path(self.banks, f"{name}-{extra_suffix}.ini"))
        try:
            return dict(data["bank"])
        except KeyError as error:
            raise ValueError(f"Bank account {name} not found!") from error

    def update_bank(self, name, **kwargs):
        filename = self.bank_path(name)
        self.ensure_dir(filename)
        if os.path.exists(filename):
            bank = RawConfigParser()
            bank.read(filename)
        else:
            bank = RawConfigParser()

        if not bank.has_section("bank"):
            bank.add_section("bank")

        for key, value in kwargs.items():
            bank.set("bank", key, value)

        with open(filename, "w") as handle:
            bank.write(handle)
        return filename

    def update_contact(  # noqa: PLR0913
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
            contact = RawConfigParser()

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
    default_due = 30

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
