import datetime
import subprocess
from argparse import ArgumentParser

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


@register_command
class List(Command):

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
            "--vat", action="store_true", help="Include VAT", default=False
        )
        parser.add_argument("match", nargs="?", help="Match string to find")
        return parser

    def match(self, invoice):
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
        total = 0
        for invoice in self.storage.list(self.args.year):
            if not self.match(invoice):
                continue
            amount = invoice.amount_czk_vat if self.args.vat else invoice.amount_czk
            print(
                "{}: {} {} ({:.2f} CZK): {} [{}]".format(
                    invoice.invoiceid,
                    invoice.amount,
                    invoice.currency,
                    amount,
                    invoice.invoice["item"],
                    invoice.contact["name"],
                )
            )
            total += amount
        print()
        print(f"Total: {total:.2f} CZK")


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
            "--vat", action="store_true", help="Include VAT", default=False
        )
        parser.add_argument("--summary", "-s", action="store_true", help="show YTD sum")
        return parser

    def run(self):
        categories = self.storage.settings["categories"].split(",")
        supertotal = 0
        year = self.args.year
        supercats = {x: 0 for x in categories}
        catformat = " ".join(f"{{{x}:7.0f}} CZK" for x in categories)
        header = "Month         Total {}".format(
            " ".join(f"{x.title():>11}" for x in categories)
        )
        print(header)
        print("-" * len(header))
        for month in range(1, 13):
            total = 0
            cats = {x: 0 for x in categories}
            for invoice in self.storage.list(year, month):
                amount = invoice.amount_czk_vat if self.args.vat else invoice.amount_czk
                cats[invoice.category] += amount
                supercats[invoice.category] += amount
                total += amount
                supertotal += amount
            if self.args.summary:
                print(
                    "{}/{:02d} {:7.0f} CZK {}".format(
                        year, month, supertotal, catformat.format(**supercats)
                    )
                )
            else:
                print(f"{year}/{month:02d} {total:7.0f} CZK {catformat.format(**cats)}")
        print("-" * len(header))
        print(f"Summary {supertotal:7.0f} CZK {catformat.format(**supercats)}")


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
            subprocess.run(["gvim", filename])


def main(args=None):
    """CLI entry point."""
    parser = ArgumentParser(
        description="Fakturace.",
        epilog="This utility is developed at <{}>.".format(
            "https://github.com/nijel/fakturace"
        ),
    )
    parser.add_argument(
        "--quotes", action="store_true", help="Operate on quotes instead of invoices"
    )
    parser.add_argument("--web", action="store_true", help="Operate on web invoices")
    parser.add_argument(
        "--proforma", action="store_true", help="Operate on proforma invoices"
    )

    subparser = parser.add_subparsers(dest="cmd")
    for command in COMMANDS:
        COMMANDS[command].add_parser(subparser)

    params = parser.parse_args(args)

    command = COMMANDS[params.cmd](params)
    command.run()


if __name__ == "__main__":
    main()
