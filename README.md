# Claude AI Usage Widget — Linux Taskbar

A lightweight system tray widget that shows your Claude AI subscription usage (5-hour and 7-day rate limit windows) directly in your Linux taskbar.

## Quick Start

```bash
git clone https://github.com/StaticB1/claude_ai_usage_widget.git && cd claude_ai_usage_widget
./install.sh
claude-widget-start
```

If you have Claude Code logged in, the token is detected automatically. Otherwise you'll be prompted to enter it.

## Features

- Taskbar percentage with color-coded icon (green/yellow/orange/red)
- Dropdown with progress bars, reset timers, and subscription plan
- Extra usage (pay-as-you-go) credit tracking
- Desktop notifications at 75%, 90%, and 100% usage
- Auto-refresh every 2 minutes
- Auto-detects Claude Code credentials
- Autostarts on login

## Install

```bash
git clone https://github.com/StaticB1/claude_ai_usage_widget.git && cd claude_ai_usage_widget
./install.sh
```

The installer checks for dependencies and offers to install them. Then:

```bash
claude-widget-start   # start
claude-widget-stop    # stop
```

## Upgrade

```bash
cd claude_ai_usage_widget
git pull
claude-widget-stop
./install.sh
claude-widget-start
```

## Uninstall

```bash
./uninstall.sh
```

## OAuth Token

**Claude Code (automatic):** If you have Claude Code installed, just run `claude login` — the widget reads `~/.claude/.credentials.json` automatically.

**Manual:** Open https://claude.ai, DevTools > Network > filter `api.anthropic.com`, copy the `Authorization: Bearer sk-ant-oat01-...` header, and enter it via the widget's "Set Token" menu.

## Troubleshooting

| Problem | Fix |
|---|---|
| No tray icon on GNOME 43+ | `sudo apt install gnome-shell-extension-appindicator` |
| `ModuleNotFoundError: gi` | Using pyenv/conda — `claude-widget-start` uses system Python |
| Token expired / 401 | Re-run `claude login` or re-extract from browser |
| Icon shows "ERR" | Check token and network connectivity |
| Logs | `cat /tmp/claude-widget.log` |

## License

MIT
