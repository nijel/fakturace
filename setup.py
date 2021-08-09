#!/usr/bin/env python3

from setuptools import setup

with open("README.rst") as handle:
    LONG_DESCRIPTION = handle.read()

with open("requirements.txt") as handle:
    REQUIRES = handle.read().split()

setup(
    name="fakturace",
    version="0.5",
    author="Michal Čihař",
    author_email="michal@cihar.com",
    description="Simple invoicing and billing tool",
    long_description=LONG_DESCRIPTION,
    long_description_content_type="text/x-rst",
    license="GPLv3+",
    keywords="billing invoice",
    url="https://cihar.com/",
    download_url="https://github.com/nijel/fakturace",
    project_urls={"Issue Tracker": "https://github.com/nijel/fakturace/issues"},
    platforms=["any"],
    packages=["fakturace"],
    package_dir={"fakturace": "fakturace"},
    install_requires=REQUIRES,
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: GNU General Public License v3 or later (GPLv3+)",
        "Operating System :: OS Independent",
        "Programming Language :: Python",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Topic :: Utilities",
    ],
    entry_points={"console_scripts": ["fakturace = fakturace.cli:main"]},
    python_requires=">=3.7",
)
