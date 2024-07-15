import datetime
import subprocess
from argparse import ArgumentParser
from fnmatch import fnmatch
from xml.etree import ElementTree

from vies.types import VATIN

from .storage import InvoiceStorage, ProformaStorage, QuoteStorage, WebStorage

COMMANDS = {}


def register_command(command):
    """Register a command in command line interface."""
    COMMANDS[command.__name__.lower()] = command
    return command


class Command:
    """Basic command object."""

    def __init__(self, args):
        """Construct Command object."""
        self.args = args
        if args.quotes:
            self.storage = QuoteStorage()
        elif args.web:
            self.storage = WebStorage()
        elif args.proforma:
            self.storage = ProformaStorage()
        else:
            self.storage = InvoiceStorage()

    @classmethod
    def add_parser(cls, subparser):
        """Create parser for command line."""
        return subparser.add_parser(cls.__name__.lower(), description=cls.__doc__)

    def run(self):
        """Execute the command."""
        raise NotImplementedError


class FilterCommand(Command):
    """List invoices."""

    @classmethod
    def add_parser(cls, subparser):
        """Create parser for command line."""
        parser = super().add_parser(subparser)
        parser.add_argument(
            "--year",
            type=int,
            help="Year to process",
            default=datetime.date.today().year,
        )
        parser.add_argument(
            "--filter",
            help="Filter by ID",
        )
        parser.add_argument(
            "--vat",
            action="store_true",
            help="Include VAT",
            default=False,
        )
        parser.add_argument("match", nargs="?", help="Match string to find")
        return parser

    def match(self, invoice):
        if self.args.filter and not fnmatch(invoice.invoiceid, self.args.filter):
            return False

        if not self.args.match:
            return True
        match = self.args.match.lower()
        return (
            match in invoice.invoice["item"].lower()
            or match in invoice.invoice["contact"].lower()
            or match in invoice.contact["name"].lower()
        )

    def list(self):
        for invoice in self.storage.list(self.args.year):
            if self.match(invoice):
                yield invoice


@register_command
class List(FilterCommand):
    """List invoices."""

    def run(self):
        """Execute the command."""
        total = 0
        for invoice in self.list():
            amount = invoice.amount_czk_vat if self.args.vat else invoice.amount_czk
            print(
                "{}: {} {} ({:.2f} CZK): {} [{}]".format(
                    invoice.invoiceid,
                    invoice.amount,
                    invoice.currency,
                    amount,
                    invoice.invoice["item"],
                    invoice.contact["name"],
                ),
            )
            total += amount
        print()
        print(f"Total: {total:.2f} CZK")


@register_command
class XMLExport(FilterCommand):
    """XML exportinvoices."""

    def add_element(self, root, name: str, text: str | None = None):
        added = ElementTree.SubElement(root, name)
        if text is not None:
            added.text = text
        return added

    def add_amounts(self, root, invoice, prefix: str = ""):
        dph = self.add_element(root, "SouhrnDPH")
        vat_rate = int(invoice.invoice["vat"])
        fixed_rates = {0, 5, 22}
        if vat_rate in fixed_rates:
            self.add_element(
                dph, f"Zaklad{vat_rate}", invoice.invoice[f"{prefix}total"]
            )
            if vat_rate > 0:
                self.add_element(
                    dph, f"DPH{vat_rate}", invoice.invoice[f"{prefix}total_vat"]
                )
            fixed_rates.remove(vat_rate)
            for rate in fixed_rates:
                self.add_element(dph, f"Zaklad{rate}", "0")
            for rate in fixed_rates:
                if rate > 0:
                    self.add_element(dph, f"DPH{rate}", "0")
        else:
            dalsi = self.add_element(dph, "SeznamDalsiSazby")
            sazba = self.add_element(dalsi, "DalsiSazba")
            self.add_element(sazba, "Sazba", invoice.invoice["vat"])
            self.add_element(sazba, "Zaklad", invoice.invoice[f"{prefix}total"])
            self.add_element(sazba, "DPH", invoice.invoice[f"{prefix}total_vat"])
        self.add_element(root, "Celkem", invoice.invoice[f"{prefix}total_sum"])

    def run(self):  # noqa: PLR0915
        """Execute the command."""
        document = ElementTree.Element("MoneyData")
        invoices = ElementTree.SubElement(document, "SeznamFaktVyd")

        for invoice in self.list():
            output = ElementTree.SubElement(invoices, "FaktVyd")
            self.add_element(output, "Doklad", invoice.invoiceid)
            self.add_element(output, "CisRada", "0")
            self.add_element(output, "Popis", invoice.invoice["item"])
            self.add_element(output, "Vystaveno", invoice.invoice["date"])
            self.add_element(output, "DatUcPr", invoice.invoice["date"])
            self.add_element(output, "PlnenoDPH", invoice.invoice["date"])
            self.add_element(output, "Splatno", invoice.invoice["due"])
            self.add_element(output, "DatSkPoh", invoice.invoice["date"])
            self.add_element(output, "KodDPH", "19Ř21")
            self.add_element(output, "ZjednD", "0")
            self.add_element(output, "VarSymbol", invoice.invoiceid)

            # Druh (N: normální, L: zálohová, F: proforma, D: doklad k přijaté platbě)
            self.add_element(output, "Druh", "N")
            self.add_element(
                output,
                "Dobropis",
                "0" if float(invoice.invoice["total_sum"]) > 0 else "1",
            )
            self.add_element(output, "ZpVypDPH", "1")
            self.add_element(output, "SazbaDPH1", "12")
            self.add_element(output, "SazbaDPH2", "21")
            self.add_element(output, "Proplatit", invoice.invoice["czk_total_sum"])
            self.add_element(output, "Vyuctovano", "0")
            self.add_amounts(output, invoice, "czk_")
            if invoice.currency != "CZK":
                valuty = self.add_element(output, "Valuty")
                mena = self.add_element(valuty, "Mena")
                self.add_element(mena, "Kod", "EUR")
                self.add_element(mena, "Mnozstvi", "1")
                self.add_element(mena, "Kurs", invoice.invoice["czk_rate"])
                self.add_amounts(valuty, invoice)

            self.add_element(output, "PriUhrZbyv", "0")
            if invoice.currency != "CZK":
                self.add_element(output, "ValutyProp", invoice.invoice["total_sum"])
            self.add_element(output, "SumZaloha", "0")
            self.add_element(output, "SumZalohaC", "0")

            prijemce = self.add_element(output, "DodOdb")
            self.add_element(prijemce, "ObchNazev", invoice.contact["name"])
            adresa = self.add_element(prijemce, "ObchAdresa")
            self.add_element(adresa, "Ulice", invoice.contact["address"])
            self.add_element(adresa, "Misto", invoice.contact["city"])
            self.add_element(adresa, "Stat", invoice.contact["country"])
            self.add_element(prijemce, "FaktNazev", invoice.contact["name"])
            if invoice.contact["tax_reg"] and invoice.contact["vat_reg"].startswith(
                "CZ"
            ):
                self.add_element(prijemce, "ICO", invoice.contact["tax_reg"])
            if invoice.contact["vat_reg"]:
                self.add_element(prijemce, "DIC", invoice.contact["vat_reg"])
            adresa = self.add_element(prijemce, "FaktAdresa")
            self.add_element(adresa, "Ulice", invoice.contact["address"])
            self.add_element(adresa, "Misto", invoice.contact["city"])
            self.add_element(adresa, "Stat", invoice.contact["country"])
            if invoice.contact["vat_reg"]:
                self.add_element(prijemce, "PlatceDPH", "1")
                self.add_element(prijemce, "FyzOsoba", "0")

            seznam = self.add_element(output, "SeznamPolozek")
            for row in invoice.invoice["rows_data"]:
                polozka = self.add_element(seznam, "Polozka")
                self.add_element(polozka, "Popis", row["item"])
                self.add_element(polozka, "PocetMJ", row["quantity"])
                if invoice.currency == "CZK":
                    self.add_element(polozka, "Cena", row["total"])
                else:
                    self.add_element(polozka, "Valuty", row["total"])

        ElementTree.indent(document)
        ElementTree.dump(document)


@register_command
class Contacts(Command):
    """List invoices."""

    @classmethod
    def add_parser(cls, subparser):
        """Create parser for command line."""
        parser = super().add_parser(subparser)
        parser.add_argument(
            "--year",
            type=int,
            help="Year to process",
            default=datetime.date.today().year,
        )
        parser.add_argument(
            "--country",
            help="Country to list",
        )
        parser.add_argument("match", nargs="?", help="Match string to find")
        return parser

    def match(self, invoice):
        if self.args.country and self.args.country != invoice.contact["country"]:
            return False
        if not self.args.match:
            return True
        match = self.args.match.lower()
        return (
            match in invoice.invoice["item"].lower()
            or match in invoice.invoice["contact"].lower()
            or match in invoice.contact["name"].lower()
        )

    def run(self):
        """Execute the command."""
        contacts = {}
        for invoice in self.storage.list(self.args.year):
            if not self.match(invoice):
                continue
            contacts[invoice.contact["name"]] = invoice.contact

        for contact in contacts.values():
            print(f"{contact['name']}, {contact['city']}, {contact.get('email')}")


@register_command
class NotPaid(List):
    """Not paid invoices."""

    def match(self, invoice):
        return not invoice.paid() and super().match(invoice)


@register_command
class Detail(Command):
    """Show invoice detail."""

    @classmethod
    def add_parser(cls, subparser):
        """Create parser for command line."""
        parser = super().add_parser(subparser)
        parser.add_argument("id", help="Invoice id")
        return parser

    def run(self):
        """Execute the command."""
        invoice = self.storage.get(self.args.id)
        print(invoice.invoiceid)
        print("-" * len(invoice.invoiceid))
        print("Date:     ", invoice.invoice["date"])
        print("Due:      ", invoice.invoice["due"])
        print("Name:     ", invoice.contact["name"])
        print("Address:  ", invoice.contact["address"])
        print("City:     ", invoice.contact["city"])
        print("Country:  ", invoice.contact["country"])
        print("Item:     ", invoice.invoice["item"])
        print("Category: ", invoice.invoice["category"])
        print(f"Rate:      {invoice.rate} {invoice.currency}")
        print(f"Quantity:  {invoice.quantity}")
        print(f"Amount:    {invoice.amount} {invoice.currency}")
        print(f"Amount:    {invoice.amount_czk:.2f} CZK incl. VAT")
        if invoice.paid():
            print("Paid:      yes")
        else:
            print("Paid:      no")


@register_command
class WriteTex(Detail):
    """Generate tex."""

    def run(self):
        """Execute the command."""
        invoice = self.storage.get(self.args.id)
        invoice.write_tex()


@register_command
class BuildPDF(Detail):
    """Build PDF."""

    def run(self):
        """Execute the command."""
        invoice = self.storage.get(self.args.id)
        invoice.build_pdf()


@register_command
class Summary(Command):
    """Show invoice summary."""

    @classmethod
    def add_parser(cls, subparser):
        parser = super().add_parser(subparser)
        parser.add_argument(
            "--year",
            type=int,
            help="Year to process",
            default=datetime.date.today().year,
        )
        parser.add_argument(
            "--vat",
            action="store_true",
            help="Include VAT",
            default=False,
        )
        parser.add_argument("--summary", "-s", action="store_true", help="show YTD sum")
        return parser

    def run(self):
        categories = self.storage.settings["categories"].split(",")
        supertotal = 0
        year = self.args.year
        supercats = dict.fromkeys(categories, 0)
        cat_format = " ".join(f"{{{x}:7.0f}} CZK" for x in categories)
        header = "Month         Total {}".format(
            " ".join(f"{x.title():>11}" for x in categories),
        )
        print(header)
        print("-" * len(header))
        for month in range(1, 13):
            total = 0
            cats = dict.fromkeys(categories, 0)
            for invoice in self.storage.list(year, month):
                amount = invoice.amount_czk_vat if self.args.vat else invoice.amount_czk
                cats[invoice.category] += amount
                supercats[invoice.category] += amount
                total += amount
                supertotal += amount
            if self.args.summary:
                display_total = supertotal
                cat_sums = cat_format.format(**supercats)
            else:
                display_total = total
                cat_sums = cat_format.format(**cats)
            print(f"{year}/{month:02d} {display_total:7.0f} CZK {cat_sums}")
        print("-" * len(header))
        print(f"Summary {supertotal:7.0f} CZK {cat_format.format(**supercats)}")


@register_command
class Add(Command):
    """Create new invoice."""

    @classmethod
    def add_parser(cls, subparser):
        """Create parser for command line."""
        parser = super().add_parser(subparser)
        parser.add_argument(
            "--skip-validation",
            "-s",
            action="store_true",
            help="Skip VAT validation",
            default=False,
        )
        parser.add_argument("--edit", "-e", action="store_true", help="open in editor")
        parser.add_argument("contact", help="Contact name")
        return parser

    def run(self):
        contact = self.storage.read_contact(self.args.contact)
        vat_reg = contact.get("vat_reg", "")
        if vat_reg:
            vat_reg = vat_reg.strip().replace(" ", "")
            vatin = VATIN(vat_reg[:2], vat_reg[2:])
            if self.args.skip_validation:
                vatin.verify()
            elif not vatin.data.valid:
                raise ValueError(f"Invalid VAT: {vat_reg}")

        filename = self.storage.create(self.args.contact)
        print(filename)
        if self.args.edit:
            subprocess.run(["gvim", filename], check=True)


def main(args=None):
    """CLI entry point."""
    parser = ArgumentParser(
        description="Fakturace.",
        epilog="This utility is developed at <{}>.".format(
            "https://github.com/nijel/fakturace",
        ),
    )
    parser.add_argument(
        "--quotes",
        action="store_true",
        help="Operate on quotes instead of invoices",
    )
    parser.add_argument("--web", action="store_true", help="Operate on web invoices")
    parser.add_argument(
        "--proforma",
        action="store_true",
        help="Operate on proforma invoices",
    )

    subparser = parser.add_subparsers(dest="cmd")
    for command in COMMANDS:
        COMMANDS[command].add_parser(subparser)

    params = parser.parse_args(args)

    command = COMMANDS[params.cmd](params)
    command.run()


if __name__ == "__main__":
    main()
