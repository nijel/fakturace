from argparse import ArgumentParser
import glob
import sys
import datetime

from fakturace.invoices import Invoice, InvoiceStorage


COMMANDS = {}


def register_command(command):
    """Decorator to register command in command line interface."""
    COMMANDS[command.__name__.lower()] = command
    return command


class Command(object):

    """Basic command object."""

    def __init__(self, args, stdout=None):
        """Construct Command object."""
        self.args = args
        if stdout is None:
            self.stdout = sys.stdout
        else:
            self.stdout = stdout
        self.storage = InvoiceStorage()

    @classmethod
    def add_parser(cls, subparser):
        """Create parser for command line."""
        return subparser.add_parser(cls.__name__.lower(), description=cls.__doc__)

    def run(self):
        """Main execution of the command."""
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
            nargs="?",
            help="Year to process",
            default=datetime.date.today().year,
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
        )

    def run(self):
        """Main execution of the command."""
        total = 0
        match = self.args.match
        for invoice in self.storage.list(self.args.year):
            if not self.match(invoice):
                continue
            print(
                "{0}: {1} {2} ({4:.2f} CZK): {3}".format(
                    invoice.invoiceid,
                    invoice.amount,
                    invoice.currency,
                    invoice.invoice["item"],
                    invoice.amount_czk,
                )
            )
            total += invoice.amount_czk
        print()
        print("Total: {0:.2f} CZK".format(total))


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
        """Main execution of the command."""
        invoice = self.storage.get(self.args.id)
        print(invoice.invoiceid)
        print("-" * len(invoice.invoiceid))
        print("Date:     ", invoice.invoice["date"])
        print("Due:      ", invoice.invoice["due"])
        print("Name:     ", invoice.contact["name"])
        print("Item:     ", invoice.invoice["item"])
        print("Category: ", invoice.invoice["category"])
        print("Rate:      {0} {1}".format(invoice.rate, invoice.currency))
        print("Quantity:  {0}".format(invoice.quantity))
        print("Amount:    {0} {1}".format(invoice.amount, invoice.currency))
        if invoice.currency != "CZK":
            print("Amount:    {0:.2f} CZK".format(invoice.amount_czk))
        if invoice.paid():
            print("Paid:      yes")
        else:
            print("Paid:      no")


def main(stdout=None, args=None):
    """Execution entry point."""
    stdout = stdout if stdout is not None else sys.stdout

    parser = ArgumentParser(
        description="Fakturace.",
        epilog="This utility is developed at <{0}>.".format(
            "https://github.com/nijel/fakturace"
        ),
    )

    subparser = parser.add_subparsers(dest="cmd")
    for command in COMMANDS:
        COMMANDS[command].add_parser(subparser)

    params = parser.parse_args(args)

    command = COMMANDS[params.cmd](params, stdout)
    command.run()
