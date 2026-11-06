#!/usr/bin/env bash
# Whale-chan reaction for Claude Code hooks: `whalechan-react.sh <event> [args...]`
# runs `whalechan -q react <event> [args...]`, but stays quiet on Stop and on
# idle_prompt Notifications while background agents/shells are still running
# (counted by the bg-pending helper; WHALECHAN_BG_PENDING overrides its path).
# Their completion re-invokes Claude, and the Stop after that is the real one.
# Every other hook event (StopFailure, permission_prompt, ...) always reacts.
# Never fails, never prints.

input=$(cat)
helper=${WHALECHAN_BG_PENDING:-$HOME/.claude/hooks/bg-pending}

# Any failure (no helper, no transcript, parse error, missing jq) is false, so she reacts as before.
bg_pending() {
  local n
  n=$("$helper" "$(jq -r '.transcript_path // empty' <<<"$input")" 2>/dev/null) || return 1
  [[ $n =~ ^[0-9]+$ ]] && (( n > 0 ))
}

case $(jq -r '.hook_event_name // empty' <<<"$input" 2>/dev/null) in
  Stop)
    bg_pending && exit 0
    ;;
  Notification)
    [[ $(jq -r '.notification_type // empty' <<<"$input" 2>/dev/null) == idle_prompt ]] && bg_pending && exit 0
    ;;
esac

whalechan -q react "$@" 2>/dev/null || true
exit 0
