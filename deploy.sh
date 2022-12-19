#!/bin/bash
#
# deploy.sh
#
# Deployment script for yfirlestur.is
#
# Prompts for confirmation before copying files over
#

SRC=~/github/Yfirlestur
DEST=/usr/share/nginx/yfirlestur.is
SERVICE=yfirlestur

read -rp "This will deploy Yfirlestur to **PRODUCTION**. Confirm? (y/n): " CONFIRMED

if [ "$CONFIRMED" != "y" ]; then
    echo "Deployment aborted"
    exit 1
fi

echo "Deploying $SRC to $DEST..."

cd $SRC || exit 1

cp requirements.txt $DEST/requirements.txt

cd $DEST || exit 1

source "venv/bin/activate"
pip install --upgrade -r requirements.txt
deactivate

cd $SRC || exit 1

echo "Copying files"

rsync -av --delete config/ $DEST/config/
rsync -av --delete db/ $DEST/db/
rsync -av --delete routes/ $DEST/routes/
rsync -av --delete templates/ $DEST/templates/
rsync -av --delete static/ $DEST/static/

cp *.py $DEST/

# Put a version identifier (date and time) into the about.html template
sed -i "s/\[Þróunarútgáfa\]/Útgáfa `date "+%Y-%m-%d %H:%M"`/g" $DEST/templates/about.html
GITVERS=$(git rev-parse HEAD) # Get git commit ID
GITVERS=${GITVERS:0:7} # Truncate it
sed -i "s/\[Git-útgáfa\]/${GITVERS}/g" $DEST/templates/about.html

echo "Reloading gunicorn server..."

sudo systemctl reload $SERVICE

echo "Deployment done"
