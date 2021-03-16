#!/usr/bin/python3

import setuptools

# From https://packaging.python.org/guides/making-a-pypi-friendly-readme/
from os import path
this_directory = path.abspath(path.dirname(__file__))
with open(path.join(this_directory, 'README.md'), encoding='utf-8') as f:
    long_description = f.read()

setuptools.setup(
    name='textoter',
    version='0.5',
    author='Arnaud Gardelein',
    author_email='arnaud@oscopy.org',
    description='Textoter is a simple application that sends SMS using a phone connected via Bluetooth',
    long_description=long_description,
    long_description_content_type='text/markdown',
    url='https://github.com/agardelein/textoter',
    project_urls={
        'Tracker':'https://github.com/agardelein/textoter/issues',
        },
    classifiers = [
        'Programming Language :: Python :: 3',
        'License :: OSI Approved :: GNU General Public License v3 (GPLv3)',
        'Topic :: Communications :: Telephony',
        'Topic :: Desktop Environment :: Gnome',
        'Intended Audience :: End Users/Desktop',
        ],
    keywords='gtk sms mms bluetooth phone send texto',
    packages=setuptools.find_packages(where='src'),
    entry_points={
    'console_scripts': [
        'textoter=textoter:main'
    ],
},
    package_dir={'': 'src'},
    python_requires='>=3',
    data_files=[
        ('share/textoter', ['data/textoter.glade']),
        ('share/applications', ['data/textoter.desktop']),
        ]
                 )

