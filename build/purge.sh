#!/bin/bash

# SPDX-FileCopyrightText: 2021 Gabriel J. Schwarzkopf <sispo-devs@outlook.com>
#
# SPDX-License-Identifier: GPL-3.0-or-later

echo "Purging software directory: Proceed [y/n]"
read -r confirmation

conda deactivate

if [ "$confirmation" = y ]
    then \
	    rm -r ../software & 
	    #rm -r ../data & \
	    wait 
	    echo "Purging software directory: done"
    else echo "Nothing done"
fi
