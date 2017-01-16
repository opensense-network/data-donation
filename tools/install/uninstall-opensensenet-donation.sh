#! /bin/sh

INSTALL_DIR=/opt/opensensenet
GIT_URL="https://github.com/fpallas/opensensenet.git"

echo "Uninstalling Opensensenet Donation Environment from $INSTALL_DIR..."
echo "Stopping Service..."
sudo /etc/init.d/opensensenet-donation stop
echo "Removing init.d-script..."
sudo update-rc.d -f opensensenet-donation remove
sudo rm /etc/init.d/opensensenet-donation
echo "Removing $INSTALL_DIR"
sudo rm -rf $INSTALL_DIR
echo "Done."