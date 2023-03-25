#!/bin/sh

set -xe

sudo apt-get update && sudo apt-get upgrade -y
sudo apt-get install -y python3-virtualenv
