# deploy/ — scheduling the nightly sleep-time loop

The sleep-time loop (`personal-llm sleep`) consolidates the vault each night:
learn new facts from transcripts (opt-in), grade them, dedup, and write a growth
log. To run it automatically, schedule it. This directory ships a portable
**systemd user timer** so the schedule travels with the repo instead of living
in one machine's crontab.

## Why a systemd timer (not cron)

`Persistent=true` (in `personal-llm-sleep.timer`): if the machine is asleep or
off at 03:00, the run fires on the next wake/boot. Plain cron silently skips a
missed run — the wrong default for a laptop.

## Install

```sh
# From the repo root. If you run from a source checkout via uv (e.g. exFAT),
# export UV_PROJECT_ENVIRONMENT first so it is baked into the unit:
#   export UV_PROJECT_ENVIRONMENT=~/.venvs/personal-llm
./deploy/install-sleep-timer.sh
```

This writes `~/.config/systemd/user/personal-llm-sleep.{service,timer}`, enables
the timer, and tries to enable lingering (so it fires without an active login).

```sh
systemctl --user list-timers personal-llm-sleep.timer   # when it runs next
systemctl --user start personal-llm-sleep.service        # run once now
journalctl --user -u personal-llm-sleep.service -e       # see output
./deploy/uninstall-sleep-timer.sh                        # remove
```

## Prerequisites

- **Enable learning** (otherwise the loop only grades/dedups existing facts):
  set `sleep.learn_from_transcripts: true` in your vault `config.yaml`.
- **Ollama** should be running for the learn / LLM-grading / dedup steps. Running
  it as a system service (`systemctl enable ollama`) means it is up by 03:00; if
  it is down, the loop still runs the deterministic grade and writes a log.

## Files

| file | role |
|---|---|
| `systemd/personal-llm-sleep.timer` | the 03:00 schedule, `Persistent=true` |
| `systemd/personal-llm-sleep.service.in` | oneshot unit template (paths filled at install) |
| `run-sleep.sh` | portable launcher — installed CLI, else `uv run` from the checkout |
| `install-sleep-timer.sh` / `uninstall-sleep-timer.sh` | (un)install the user units |

## cron alternative

If you prefer cron (no missed-run catch-up):

```cron
0 3 * * * personal-llm sleep >> ~/.personal-llm/sleep-cron.log 2>&1
```
