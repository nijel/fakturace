from tempfile import TemporaryDirectory
from unittest import TestCase

from .storage import InvoiceStorage


class InvoiceStorageTest(TestCase):
    def test_list(self):
        with TemporaryDirectory() as testdir:
            storage = InvoiceStorage(testdir)
            assert len(list(storage.list())) == 0

    def test_contact_invoice(self):
        with TemporaryDirectory() as testdir:
            storage = InvoiceStorage(testdir)

            # Create bank
            storage.update_bank("EUR", bank="Test")

            # Create contact
            storage.update_contact(
                "test",
                "Name",
                "Address",
                "City",
                "Country",
                "noreply@example.com",
                "",
                "",
                "EUR",
                "test",
            )
            assert storage.read_contact("test")["name"] == "Name"

            # Create invoice
            storage.create("test", rate="100", item="Test item")

            # List it
            invoices = list(storage.list())
            assert len(invoices) == 1
