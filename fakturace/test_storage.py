from tempfile import TemporaryDirectory
from unittest import TestCase

from .storage import InvoiceStorage


class InvoiceStorageTest(TestCase):
    def test_list(self):
        with TemporaryDirectory() as testdir:
            storage = InvoiceStorage(testdir)
            assert len(list(storage.list())) == 0
