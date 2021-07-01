import os
import subprocess
from configparser import ConfigParser

from django.utils.functional import cached_property
from jinja2.exceptions import TemplateNotFound

from .data import CONTACT, DEFAULTS
from .rates import Rates


class Invoice:
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
        """Load data from ini files."""
        data = ConfigParser()
        data.read(self.name)

        self.invoice = dict(data["invoice"])

        self.contact = self.storage.read_contact(self.invoice["contact"])

        self.process_defaults()

        self.bank = self.storage.read_bank(
            self.invoice["currency"], self.invoice["bank_suffix"]
        )
        # Propagate defaults from bank
        for field in ("template", "note", "vat"):
            if field in self.bank:
                self.invoice[field] = self.bank[field]

        # Fetch invoice rows
        self.invoice["rows_data"] = []
        total_sum = 0
        for suffix in (
            "",
            "_2",
            "_3",
            "_4",
            "_5",
            "_6",
            "_7",
            "_8",
            "_9",
            "_10",
            "_11",
            "_12",
            "_13",
            "_14",
            "_15",
            "_16",
            "_17",
            "_18",
            "_19",
        ):
            if "item" + suffix not in self.invoice:
                break
            quantity = self.invoice.get("quantity" + suffix, "1")
            try:
                rate = float(self.invoice["rate" + suffix])
            except KeyError:
                rate = float(self.invoice["rate"])
            total = float(quantity.split()[0]) * rate
            total_sum += total
            self.invoice["rows_data"].append(
                {
                    "item": self.invoice["item" + suffix],
                    "rate": "{0:.2f}".format(rate),
                    "quantity": quantity,
                    "total": "{0:.2f}".format(total),
                    "currency": self.invoice["currency"],
                }
            )

        self.invoice["total"] = "{0:.2f}".format(total_sum)

        # Calculate VAT
        vat = int(self.invoice["vat"]) * total_sum / 100
        if int(self.invoice["vat"]):
            self.invoice["total_vat"] = "{0:.2f}".format(vat)
            self.invoice["total_sum"] = "{0:.2f}".format(total_sum + vat)
        self.invoice["include_czk"] = bool(int(self.invoice["vat"])) and self.contact[
            "vat_reg"
        ].startswith("CZ")

        # Rates in CZK
        if self.invoice["include_czk"]:
            rate = Rates.get(self.invoice["date"], self.currency)
            self.invoice["czk_rate"] = str(rate)
            self.invoice["czk_total"] = "{0:.2f}".format(rate * total_sum)
            self.invoice["czk_total_vat"] = "{0:.2f}".format(rate * vat)
            self.invoice["czk_total_sum"] = "{0:.2f}".format(rate * (total_sum + vat))

        # Shorter summary for PDF title
        self.invoice["shortitem"] = self.invoice["item"].split(":")[0]

        remarks = []
        for pos in range(1, 10):
            name = "remark_{}".format(pos)
            if name not in self.invoice:
                break
            remarks.append(self.invoice[name])
        self.invoice["remarks"] = remarks

    def process_defaults(self):
        """Fill in default values."""
        for key, value in self.contact.items():
            if not key.startswith("default_"):
                continue
            name = key[8:]
            if name in self.invoice:
                continue
            self.invoice[name] = value
        for key, value in self.override.items():
            if key not in self.invoice:
                self.invoice[key] = value
        for key, value in DEFAULTS.items():
            if key not in self.invoice:
                self.invoice[key] = value
        for key, value in CONTACT.items():
            if key not in self.contact:
                self.contact[key] = value

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

        category_template = self.invoice["template"].replace(
            ".tex", f"-{self.category}.tex"
        )

        try:
            template = self.storage.jinja.get_template(category_template)
        except TemplateNotFound:
            template = self.storage.jinja.get_template(self.invoice["template"])

        rows = []
        for row in self.invoice["rows_data"]:
            rows.append(row_template.render(row))

        context = {"invoiceid": self.invoiceid, "rows": "\n".join(rows)}
        context.update(self.contact)
        context.update(self.invoice)
        context.update(self.bank)
        output = template.render(context)
        self.storage.ensure_dir(self.tex_path)
        with open(self.tex_path, "w") as handle:
            handle.write(output)

    def build_pdf(self):
        self.storage.ensure_dir(self.pdf_path)
        subprocess.run(
            ["xelatex", os.path.abspath(self.tex_path)],
            check=True,
            cwd=self.storage.path(self.storage.pdf),
        )

    @property
    def category(self):
        return self.invoice["category"]

    @property
    def amount(self):
        return self.invoice["total"]

    @property
    def total_amount(self):
        if "total_sum" in self.invoice:
            return self.invoice["total_sum"]
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

    @property
    def amount_czk_vat(self):
        rate = Rates.get(self.invoice["date"], self.currency)
        if "total_sum" in self.invoice:
            total = self.invoice["total_sum"]
        else:
            total = self.invoice["total"]
        return float(total) * rate

    def paid(self):
        return os.path.exists(self.name.replace(".ini", ".paid"))

    @cached_property
    def paid_path(self):
        return self.storage.path(self.storage.data, "{}.paid".format(self.invoiceid))

    def mark_paid(self, text):
        with open(self.paid_path, "w") as handle:
            handle.write(text)


class Quote(Invoice):
    def __init__(self, storage, data):
        super().__init__(
            storage,
            data,
            {
                "template": "template/quote.tex",
                "note": (
                    "Should you have any questions concerning this quotation, "
                    "please contact us at sales@weblate.org."
                ),
            },
        )


class Proforma(Invoice):
    def __init__(self, storage, data):
        super().__init__(
            storage,
            data,
            {
                "template": "template/proforma.tex",
                "note": (
                    "This is not a tax invoice, "
                    "you will receive proper invoice upon payment."
                ),
            },
        )

    def process_defaults(self):
        super().process_defaults()
        self.invoice["bank_suffix"] = "proforma"
