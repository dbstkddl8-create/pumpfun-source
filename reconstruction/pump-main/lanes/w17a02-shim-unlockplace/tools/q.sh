#!/bin/bash
# q.sh <queuefile>: two workers (slots 0/1) run "name genes" lines via run.sh; a line is claimed with mkdir lock
OUT=/Users/shawwalters/.cache/pumpfun-reconstruction/lanes/w17a02-shim-unlockplace; Q=$1; mkdir -p $OUT/claim
w(){ while read -r n g; do [ -z "$n" ] && continue; mkdir $OUT/claim/$n 2>/dev/null || continue; $OUT/tools/run.sh $n "$g" $1 > /dev/null; done < $Q; }
w 0 & w 1 & wait; echo "QDONE $Q" >> $OUT/res/R.txt
