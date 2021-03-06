#!/bin/bash

# SPDX-FileCopyrightText: 2021 Gabriel J. Schwarzkopf <sispo-devs@outlook.com>
#
# SPDX-License-Identifier: GPL-3.0-or-later

echo "Installing openMVG start"

# create dir
cd ../.. || exit
[[ -d software ]] || mkdir software
cd software || exit

[[ -d openMVG ]] || mkdir openMVG
cd openMVG || exit

# Clone git repo
git clone --recursive https://github.com/openMVG/openMVG.git

# Building
[[ -d build_openMVG ]] || mkdir build_openMVG
cd build_openMVG || exit

cmake \
	-S ../openMVG/src \
        -DCMAKE_TOOLCHAIN_FILE=../../vcpkg/scripts/buildsystems/vcpkg.cmake \
        -DCMAKE_INSTALL_PREFIX=install/ \
        -DINCLUDE_INSTALL_DIR=install/include \
        -DPYTHON_EXECUTABLE=../../conda/envs/sispo/bin/python

cmake --build . --target install

echo "Installing openMVG done"
