#!/bin/sh
INSTALL_DIR=/opt/python-openzwave
cd $INSTALL_DIR
make update
make build
sudo make clean
echo "Pythonized OpenZwave updated in  $INSTALL_DIR !"
