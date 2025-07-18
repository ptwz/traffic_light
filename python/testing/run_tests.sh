#!/bin/sh

cd "$(dirname $(readlink -f $0))/.." || exit

behave -w  $@ testing/features
