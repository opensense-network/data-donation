#!/bin/sh

INSTALL_DIR=/opt/python-openzwave
sudo apt-get install -y git-core libudev-dev libjson0 libjson0-dev libcurl4-gnutls-dev
sudo apt-get install -y git make
mkdir $INSTALL_DIR
git clone https://github.com/OpenZWave/python-openzwave $INSTALL_DIR
cd $INSTALL_DIR
sudo make repo-deps
sudo make install
echo "Pythonized OpenZwave installed to $INSTALL_DIR !"
