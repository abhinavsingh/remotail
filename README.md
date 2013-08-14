Remotail
========

Tail multiple remote files on terminal window

Install
-------

To install remotail, simply:

	$ pip install remotail

This will add an executable script `remotail.py` inside your python environment bin folder.

Usage
-----

	$ remotail.py -h
	
	usage: remotail.py [-h] [--file-path FILE_PATH] [--config CONFIG]
	
	optional arguments:
	  -h, --help            show this help message and exit
	  --file-path FILE_PATH alias://user:pass@host:port/file/path/to/tail
	  --config CONFIG       Config file containing one --file-path per line

Watch [this demo](http://ascii.io/a/4737) for example usage.