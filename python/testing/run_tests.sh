#!/bin/sh

cd "$(dirname $(readlink -f $0))/.." || exit

behave  $@ testing/features
