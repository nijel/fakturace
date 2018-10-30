import os

DEFAULTS = {
    'quantity': '1',
    'currency': 'EUR',
    'currency_note': '',
    'note': '',
    'category': 'none',
    'template': 'template/invoice.tex',
    'row': 'template/row.tex',
}
CONTACT = {
    'vat_reg': '',
    'tax_reg': '',
}
RATE_URL = 'http://www.cnb.cz/cs/financni_trhy/devizovy_trh/kurzy_devizoveho_trhu/denni_kurz.txt?date={2}.{1}.{0}'
CACHE_DIR = os.path.expanduser('~/.cache/fakturace')
