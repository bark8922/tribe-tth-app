#!/usr/bin/env bash
# Keboola runs this once on deploy to install dependencies before starting the app.
set -e
pip install -r requirements.txt
