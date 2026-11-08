#!/usr/bin/env bash

msg=$(whalechan status)
pingme telegram --token $(pass show telegram/token/teto) --channel $(pass show telegram/id/me) --msg "$msg"

