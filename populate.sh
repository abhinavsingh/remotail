#!/bin/bash

## Populates provided local file paths with some data 
## to be used for development of remotail.py
## 
## Usage: ./populate /file/path.log /another/file/path.log ...

if [ "$#" == 0 ]; then
	echo "Atleast one filepath is required."
	exit 1
fi

while true; do
	NOW=$(date)
	for f in "$@"; do
		echo $NOW > $f
	done
	sleep 0.5
done

exit 0