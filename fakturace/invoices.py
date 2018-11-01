# -*- coding: utf-8 -*-
import os
from subprocess import Popen
from configparser import ConfigParser

from fakturace.data import DEFAULTS, CONTACT
from fakturace.rates import Rates
from fakturace.utils import cached_property


class Invoice(object):
    def __init__(self, storage, data, override=None):
        self.name = data
        self.storage = storage
        self.contact = {}
        self.invoice = {}
        self.bank = {}
        if override is None:
            self.override = {}
        else:
            self.override = override
        self.load()

    def load(self):
        """Loads data from ini files"""
        data = ConfigParser()
        data.read(self.name)

        self.invoice = dict(data["invoice"])

        data = ConfigParser()
        data.read(os.path.join("contacts", "{0}.ini".format(self.invoice["contact"])))

        self.contact = dict(data["contact"])

        self.process_defaults()

        data = ConfigParser()
        data.read(os.path.join("banks", "{0}.ini".format(self.invoice["currency"])))

        self.bank = dict(data["bank"])
        # Propagate defaults from bank
        for field in ("template", "note", "vat"):
            if field in self.bank:
                self.invoice[field] = self.bank[field]

        # Fetch invoice rows
        self.invoice["rows_data"] = []
        total_sum = 0
        for suffix in ("", "_2", "_3", "_4", "_5", "_6"):
            if "item" + suffix not in self.invoice:
                break
            quantity = self.invoice.get("quantity" + suffix, "1")
            rate = self.invoice["rate" + suffix]
            total = round(float(quantity.split()[0]) * float(rate), 2)
            total_sum += total
            self.invoice["rows_data"].append(
                {
                    "item": self.invoice["item" + suffix],
                    "rate": rate,
                    "quantity": quantity,
                    "total": "{0:.2f}".format(total),
                    "currency": self.invoice["currency"],
                }
            )

        self.invoice["total"] = "{0:.2f}".format(round(total_sum, 2))

        # Calculate VAT
        total = float(self.invoice["total"])
        if int(self.invoice['vat']):
            vat = round(int(self.invoice['vat']) * total / 100, 2)
            self.invoice["total_vat"] = "{0:.2f}".format(vat)
            self.invoice["total_sum"] = "{0:.2f}".format(total + vat)

        # Shorter summary for PDF title
        self.invoice["shortitem"] = self.invoice["item"].split(":")[0]

    def process_defaults(self):
        """Fills in default values"""
        for key in self.contact.keys():
            if not key.startswith("default_"):
                continue
            name = key[8:]
            if name in self.invoice:
                continue
            self.invoice[name] = self.contact[key]
        for key in self.override.keys():
            if key not in self.invoice:
                self.invoice[key] = self.override[key]
        for key in DEFAULTS.keys():
            if key not in self.invoice:
                self.invoice[key] = DEFAULTS[key]
        for key in CONTACT.keys():
            if key not in self.contact:
                self.contact[key] = CONTACT[key]

    @cached_property
    def invoiceid(self):
        return os.path.splitext(os.path.basename(self.name))[0]

    @cached_property
    def tex_path(self):
        return self.storage.path(self.storage.tex, "{}.tex".format(self.invoiceid))

    @cached_property
    def pdf_path(self):
        return self.storage.path(self.storage.pdf, "{}.pdf".format(self.invoiceid))

    def write_tex(self):
        row_template = self.storage.jinja.get_template(self.invoice["row"])

        template = self.storage.jinja.get_template(self.invoice["template"])

        rows = []
        for row in self.invoice["rows_data"]:
            rows.append(row_template.render(row))

        context = {"invoiceid": self.invoiceid, "rows": "\n".join(rows)}
        context.update(self.contact)
        context.update(self.invoice)
        context.update(self.bank)
        output = template.render(context)
        with open(self.tex_path, "w") as handle:
            handle.write(output)

    def build_pdf(self):
        cmd = Popen(
            ["pdflatex", os.path.abspath(self.tex_path)],
            cwd=self.storage.path(self.storage.pdf),
        )
        cmd.communicate()

    @property
    def category(self):
        return self.invoice["category"]

    @property
    def amount(self):
        return self.invoice["total"]

    @property
    def currency(self):
        return self.invoice["currency"].split("-")[0]

    @property
    def rate(self):
        return self.invoice["rate"]

    @property
    def quantity(self):
        return self.invoice["quantity"]

    @property
    def amount_czk(self):
        rate = Rates.get(self.invoice["date"], self.currency)
        return float(self.invoice["total"]) * rate

    def paid(self):
        return os.path.exists(self.name.replace(".ini", ".paid"))


class Quote(Invoice):
    def __init__(self, storage, data):
        super().__init__(
            storage,
            data,
            {
                "template": "template/quote.tex",
                "note": "If you have any questions concerning this quotation, contact Michal Čihař, michal@cihar.com.",
            },
        )
