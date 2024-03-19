#!/bin/bash

manuka-manage db upgrade

echo "** Starting Apache **"
/usr/sbin/apache2ctl -D FOREGROUND
