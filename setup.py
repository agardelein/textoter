#!/usr/bin/python3

import setuptools
from os import path

def get_long_description():
    # From https://packaging.python.org/guides/making-a-pypi-friendly-readme/
    this_directory = path.abspath(path.dirname(__file__))
    with open(path.join(this_directory, 'README.md'), encoding='utf-8') as f:
        long_description = f.read()
    return long_description

setuptools.setup(
    long_description=get_long_description(),
)
