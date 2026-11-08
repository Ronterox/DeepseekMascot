#!/usr/bin/env bash

while true; do
	sleep $((30 + RANDOM % 180))
	mood=$(whalechan status | jq -r '.mood')
	whalechan mood angry
	whalechan say "Blink nowww!!"
	sleep 3
	whalechan mood $mood
done
