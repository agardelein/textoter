#!/usr/bin/python3

import setuptools

setuptools.setup(
    packages=setuptools.find_packages(where='src'),
    entry_points={
    'console_scripts': [
        'textoter=textoter:main'
    ],
},
    package_dir={'': 'src'},
    data_files = [
        ('share/textoter', ['data/textoter.glade'])
        ]
                 )

