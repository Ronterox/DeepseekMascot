#!/usr/bin/env bash
# Whale-chan reaction for Claude Code hooks: `whalechan-react.sh <event> [args...]`
# runs `whalechan -q react <event> [args...]`, except that on Stop and on
# idle_prompt Notifications with background agents/shells still running
# (counted by the bg-pending helper; WHALECHAN_BG_PENDING overrides its path)
# she waits for them instead (`react waiting`, foot tapping, no line). Their
# completion re-invokes Claude, and the Stop after that is the real one.
# Every other hook event (StopFailure, permission_prompt, ...) reacts as given.
# Never fails, never prints.

input=$(cat)
helper=${WHALECHAN_BG_PENDING:-$HOME/.claude/hooks/bg-pending}

# Any failure (no helper, no transcript, parse error, missing jq) is false, so she reacts as given.
bg_pending() {
  local n
  n=$("$helper" "$(jq -r '.transcript_path // empty' <<<"$input")" 2>/dev/null) || return 1
  [[ $n =~ ^[0-9]+$ ]] && (( n > 0 ))
}

wait_for_background() {
  whalechan -q react waiting --quiet-line 2>/dev/null || true
  exit 0
}

case $(jq -r '.hook_event_name // empty' <<<"$input" 2>/dev/null) in
  Stop)
    bg_pending && wait_for_background
    ;;
  Notification)
    [[ $(jq -r '.notification_type // empty' <<<"$input" 2>/dev/null) == idle_prompt ]] && bg_pending && wait_for_background
    ;;
esac

whalechan -q react "$@" 2>/dev/null || true
exit 0
