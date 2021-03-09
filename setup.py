#!/usr/bin/python3

import setuptools

setuptools.setup(
    name='textoter',
    version='0.9',
    author='Arnaud Gardelein',
    author_email='arnaud@oscopy.org',
    description='A stupid application to send SMS using Bluetooth Phone',
    long_description='file: README.md',
    long_description_content_type='text/markdown',
    url='https://github.com/agardelein/textoter',
    project_urls={
        'Tracker':'https://github.com/agardelein/textoter/issues',
        },
    classifiers = [
        'Programming Language :: Python :: 3',
        'License :: OSI Approved :: MIT License',
        'operating System :: Linux',
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
        ]
                 )

