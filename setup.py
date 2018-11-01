#!/usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import unicode_literals
import os
import sys
from setuptools import setup

setup(
    name="fakturace",
    version="0.1",
    author="Michal Čihař",
    author_email="michal@cihar.com",
    description="A translation finder for Weblate, translation tool with tight version control integration",
    license="MIT",
    url="https://cihar.com/",
    download_url="https://github.com/nijel/fakturace",
    platforms=["any"],
    packages=["fakturace"],
    package_dir={"fakturace": "fakturace"},
    classifiers=[
        "Development Status :: 4 - Beta",
        "Topic :: Utilities",
        "Operating System :: OS Independent",
        "Intended Audience :: Developers",
        "Programming Language :: Python :: 3",
    ],
    entry_points={"console_scripts": ["fakturace = fakturace.cli:main"]},
)
