#!/usr/bin/env bash

vars=$(whalechan input "Blink reminder" MIN_GAP=30 MAX_GAP=210 MESSAGE="Blink nowww!!") || exit
eval "$vars"
[[ $MIN_GAP =~ ^[0-9]+$ && $MAX_GAP =~ ^[0-9]+$ ]] && ((MAX_GAP >= MIN_GAP)) || { whalechan say "Blink reminder: gaps must be whole seconds, min ≤ max."; exit 1; }

read -r width height < <(xdotool getdisplaygeometry)
x=$((width / 2))
y=$((height / 2))

while true; do
	sleep $((MIN_GAP + RANDOM % (MAX_GAP - MIN_GAP + 1)))
	visible=  # stays empty if she isn't running, so the check below skips
	eval "$(whalechan status | jq -r '@sh "mood=\(.mood) wx=\(.x) wy=\(.y) sleeping=\(.sleeping) visible=\(.visible)"')"
	# let her nap, and don't drag her out while she's hidden
	[[ $sleeping == true || $visible != true ]] && continue

	# borrow angry only when she's idle; thinking/waiting belong to someone else
	# (an agent hook), and setting them again would restart their escalation
	borrow=()
	[[ $mood == neutral ]] && borrow=(-m angry)

	whalechan move $x $y
	whalechan say -d 2.5 "${borrow[@]}" "$MESSAGE"
	sleep 3
	whalechan move $wx $wy
	# give it back only if nobody changed her mood meanwhile
	[[ ${#borrow[@]} -gt 0 && $(whalechan status | jq -r .mood) == angry ]] && whalechan mood neutral
done
