# -*- coding: utf-8 -*-
"""
    remotail.py
    ~~~~~~~~~~~

    Tail multiple remote files on a terminal window

    :copyright: (c) 2013 by Abhinav Singh.
    :license: BSD, see LICENSE for more details.
"""
from setuptools import setup
import remotail

classifiers = [
    'Development Status :: 4 - Beta',
    'Environment :: Console',
    'Environment :: Console :: Curses',
    'Intended Audience :: Developers',
    'Intended Audience :: System Administrators',
    'License :: OSI Approved :: BSD License',
    'Operating System :: MacOS',
    'Operating System :: POSIX',
    'Operating System :: Unix',
    'Programming Language :: Python :: 2.7',
    'Topic :: System :: Monitoring',
    'Topic :: Utilities',
]

install_requires = open('requirements.txt', 'rb').read().strip().split()

setup(
    name                = 'remotail',
    version             = remotail.__version__,
    description         = remotail.__description__,
    long_description    = open('README.md').read().strip(),
    author              = remotail.__author__,
    author_email        = remotail.__author_email__,
    url                 = remotail.__homepage__,
    license             = remotail.__license__,
    py_modules          = ['remotail'],
    scripts             = ['remotail.py'],
    install_requires    = install_requires,
    classifiers         = classifiers
)