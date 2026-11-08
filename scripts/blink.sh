#!/usr/bin/env bash

vars=$(whalechan input "Blink reminder" MIN_GAP=30 MAX_GAP=210 MESSAGE="Blink nowww!!") || exit
eval "$vars"
[[ $MIN_GAP =~ ^[0-9]+$ && $MAX_GAP =~ ^[0-9]+$ ]] && ((MAX_GAP >= MIN_GAP)) || { whalechan say "Blink reminder: gaps must be whole seconds, min ≤ max."; exit 1; }

while true; do
	sleep $((MIN_GAP + RANDOM % (MAX_GAP - MIN_GAP + 1)))
	mood=$(whalechan status | jq -r '.mood')
	whalechan mood angry
	whalechan say "$MESSAGE"
	sleep 3
	whalechan mood $mood
done
