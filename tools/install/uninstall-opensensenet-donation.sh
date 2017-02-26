#! /bin/sh

INSTALL_DIR=/opt/opensensenet
USER=opensense

echo "Uninstalling Opensensenet Donation Environment from $INSTALL_DIR..."
echo "Stopping Service..."
sudo /etc/init.d/opensensenet-donation stop
echo "Removing init.d-script..."
sudo update-rc.d -f opensensenet-donation remove
sudo rm /etc/init.d/opensensenet-donation
echo "Removing $INSTALL_DIR"
sudo rm -rf $INSTALL_DIR
echo "Removing user and group"
sudo deluser $USER
sudo delgroup $USER
echo "Done."
