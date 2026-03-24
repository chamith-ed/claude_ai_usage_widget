#!/usr/bin/env python3
"""
Claude AI Usage Widget — Linux System Tray
Shows claude.ai subscription usage (5h / 7d) in the taskbar.

Auth: auto-detects ~/.claude/.credentials.json, or manual token entry.
"""

__version__ = "2.0.0"

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('AppIndicator3', '0.1')
gi.require_version('Notify', '0.7')

from gi.repository import Gtk, AppIndicator3, GLib, Notify
import cairo
import json
import os
import sys
import urllib.request
import urllib.error
import ssl
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

APP_ID = "claude-usage-widget"
APP_NAME = "Claude Usage"
REFRESH_SEC = 120
USAGE_URL = "https://api.anthropic.com/api/oauth/usage"
CONFIG_DIR = Path.home() / ".config" / APP_ID
CONFIG_FILE = CONFIG_DIR / "config.json"
CREDENTIALS_FILE = Path.home() / ".claude" / ".credentials.json"
ICON_DIR = Path("/tmp") / APP_ID

COLORS = {"green": "#22c55e", "yellow": "#eab308", "orange": "#f97316", "red": "#ef4444", "gray": "#6b7280"}

THRESHOLDS = [
    (100, "🛑 Claude Usage: 100%", "Rate limit reached!", "dialog-error", Notify.Urgency.CRITICAL),
    (90,  "⚠️ Claude Usage: 90%",  "Close to rate limits!", "dialog-warning", Notify.Urgency.CRITICAL),
    (75,  "⚠️ Claude Usage: 75%",  "Approaching rate limits.", "dialog-warning", Notify.Urgency.NORMAL),
]


def color_for_pct(pct):
    if pct < 0.5: return COLORS["green"]
    if pct < 0.75: return COLORS["yellow"]
    if pct < 0.9: return COLORS["orange"]
    return COLORS["red"]


def make_bar(pct, width=20):
    filled = max(0, min(width, round(pct / 100 * width)))
    return "█" * filled + "░" * (width - filled)


def format_reset(iso_str):
    if not iso_str:
        return "unknown"
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        secs = int((dt - datetime.now(timezone.utc)).total_seconds())
        if secs <= 0:
            return "any moment"
        d, r = divmod(secs, 86400)
        h, r = divmod(r, 3600)
        m = r // 60
        if d > 0: return f"{d}d {h}h"
        if h > 0: return f"{h}h {m}m"
        return f"{m}m"
    except Exception:
        return iso_str


def write_icon(pct, error=False):
    c = COLORS["gray"] if error else color_for_pct(pct)
    h = c.lstrip('#')
    r, g, b = (int(h[i:i+2], 16) / 255.0 for i in (0, 2, 4))

    size = 32
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, size, size)
    ctx = cairo.Context(surface)

    ctx.set_operator(cairo.OPERATOR_CLEAR)
    ctx.paint()
    ctx.set_operator(cairo.OPERATOR_OVER)

    # Filled circle background
    ctx.set_source_rgba(r, g, b, 0.25)
    ctx.arc(16, 16, 13, 0, 6.2832)
    ctx.fill()

    # Circle border
    ctx.set_source_rgb(r, g, b)
    ctx.set_line_width(2)
    ctx.arc(16, 16, 13, 0, 6.2832)
    ctx.stroke()

    # "C" letter
    ctx.select_font_face("Sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
    ctx.set_font_size(22)
    ext = ctx.text_extents("C")
    ctx.move_to(16 - ext.width / 2 - ext.x_bearing, 16 - ext.height / 2 - ext.y_bearing)
    ctx.show_text("C")

    ICON_DIR.mkdir(exist_ok=True)
    path = str(ICON_DIR / "icon.png")
    surface.write_to_png(path)
    return path


def _read_credentials():
    if CREDENTIALS_FILE.exists():
        try:
            return json.loads(CREDENTIALS_FILE.read_text()).get("claudeAiOauth", {})
        except (json.JSONDecodeError, KeyError):
            pass
    return {}


def load_token():
    token = _read_credentials().get("accessToken")
    if token:
        return token
    if CONFIG_FILE.exists():
        try:
            return json.loads(CONFIG_FILE.read_text()).get("oauth_token")
        except (json.JSONDecodeError, KeyError):
            pass
    return None


def load_subscription_type():
    return _read_credentials().get("subscriptionType", "").title() or None


def save_token(token):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    config = {}
    if CONFIG_FILE.exists():
        try:
            config = json.loads(CONFIG_FILE.read_text())
        except json.JSONDecodeError:
            pass
    config["oauth_token"] = token
    CONFIG_FILE.write_text(json.dumps(config, indent=2))
    os.chmod(CONFIG_FILE, 0o600)


class RateLimitError(Exception):
    pass


def fetch_usage(token):
    req = urllib.request.Request(USAGE_URL, method="GET", headers={
        "Accept": "application/json",
        "Authorization": f"Bearer {token}",
        "anthropic-beta": "oauth-2025-04-20",
    })
    try:
        with urllib.request.urlopen(req, context=ssl.create_default_context(), timeout=15) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        if e.code == 429:
            raise RateLimitError()
        print(f"[claude-usage] HTTP {e.code}: {e.reason}", file=sys.stderr)
    except Exception as e:
        print(f"[claude-usage] Error: {e}", file=sys.stderr)
    return None


class ClaudeUsageApp:
    def __init__(self):
        self.token = load_token()
        self.sub_type = load_subscription_type()
        self.usage_data = None
        self.last_updated_dt = None
        self.running = True
        self.last_notified_threshold = 0
        self.startup_notified = False

        Notify.init(APP_NAME)

        icon_path = write_icon(0, error=True)
        self.indicator = AppIndicator3.Indicator.new(
            APP_ID, icon_path, AppIndicator3.IndicatorCategory.APPLICATION_STATUS)
        self.indicator.set_status(AppIndicator3.IndicatorStatus.ACTIVE)
        self.indicator.set_title(APP_NAME)
        self.indicator.set_label("--", "")

        self._build_menu()

        if not self.token:
            GLib.timeout_add_seconds(2, self._prompt_token)
        GLib.timeout_add_seconds(30, self._tick_updated_label)
        threading.Thread(target=self._poll_loop, daemon=True).start()

    def _build_menu(self):
        self.menu = Gtk.Menu()

        self.item_sub = Gtk.MenuItem(label="")
        self.item_sub.set_sensitive(False)
        self.item_sub.set_no_show_all(True)
        self.menu.append(self.item_sub)

        self.item_5h = Gtk.MenuItem(label="5h: --%")
        self.item_5h.set_sensitive(False)
        self.menu.append(self.item_5h)

        self.item_7d = Gtk.MenuItem(label="7d: --%")
        self.item_7d.set_sensitive(False)
        self.menu.append(self.item_7d)

        self.item_extra = Gtk.MenuItem(label="")
        self.item_extra.set_sensitive(False)
        self.item_extra.set_no_show_all(True)
        self.menu.append(self.item_extra)

        self.menu.append(Gtk.SeparatorMenuItem())

        self.item_updated = Gtk.MenuItem(label="Updated: never")
        self.item_updated.set_sensitive(False)
        self.menu.append(self.item_updated)

        item_refresh = Gtk.MenuItem(label="↻ Refresh")
        item_refresh.connect("activate", lambda _: self._refresh())
        self.menu.append(item_refresh)

        item_token = Gtk.MenuItem(label="Set Token…")
        item_token.connect("activate", lambda _: self._prompt_token())
        self.menu.append(item_token)

        self.menu.append(Gtk.SeparatorMenuItem())

        item_quit = Gtk.MenuItem(label="Quit")
        item_quit.connect("activate", lambda _: self._quit())
        self.menu.append(item_quit)

        self.menu.show_all()
        self.indicator.set_menu(self.menu)

    def _poll_loop(self):
        while self.running:
            try:
                fresh = load_token()
                if fresh:
                    self.token = fresh
                if self.token:
                    data = fetch_usage(self.token)
                    GLib.idle_add(self._update_ui, data)
            except RateLimitError:
                print("[claude-usage] Rate limited, backing off 10 min", file=sys.stderr)
                GLib.idle_add(self._update_ui, None)
                time.sleep(600)
                continue
            except Exception as e:
                print(f"[claude-usage] Poll error: {e}", file=sys.stderr)
            time.sleep(REFRESH_SEC)

    def _refresh(self):
        def do():
            if self.token:
                GLib.idle_add(self._update_ui, fetch_usage(self.token))
        threading.Thread(target=do, daemon=True).start()

    def _tick_updated_label(self):
        if self.last_updated_dt:
            ago = int((datetime.now() - self.last_updated_dt).total_seconds() // 60)
            ts = self.last_updated_dt.strftime("%-I:%M %p")
            if ago == 0: ago_s = "just now"
            elif ago == 1: ago_s = "1 min ago"
            else: ago_s = f"{ago} mins ago"
            self.item_updated.set_label(f"Updated: {ts} ({ago_s})")
        return True

    def _update_ui(self, data):
        self.usage_data = data
        self.last_updated_dt = datetime.now()
        self._tick_updated_label()

        if not data:
            self.indicator.set_label("ERR", "")
            self.indicator.set_icon_full(write_icon(0, error=True), "Error")
            self.item_5h.set_label("5h: error")
            self.item_7d.set_label("7d: error")
            return False

        if self.sub_type:
            self.item_sub.set_label(f"Plan: {self.sub_type}")
            self.item_sub.show()

        five = data.get("five_hour") or {}
        seven = data.get("seven_day") or {}
        pct5, pct7 = int(five.get("utilization", 0)), int(seven.get("utilization", 0))
        dominant = max(pct5, pct7) / 100

        self.indicator.set_label(f"{pct5}%", "")
        self.indicator.set_icon_full(write_icon(dominant), f"{pct5}%")
        self.item_5h.set_label(f"5h: {make_bar(pct5)} {pct5:3d}%  resets {format_reset(five.get('resets_at'))}")
        self.item_7d.set_label(f"7d: {make_bar(pct7)} {pct7:3d}%  resets {format_reset(seven.get('resets_at'))}")

        extra = data.get("extra_usage") or {}
        if extra.get("is_enabled"):
            self.item_extra.set_label(f"Extra: {extra.get('used_credits', 0):.0f}/{extra.get('monthly_limit', 0):.0f} credits")
            self.item_extra.show()
        else:
            self.item_extra.hide()

        self._notify(pct5, pct7, dominant)
        return False

    def _notify(self, pct5, pct7, dominant):
        usage_str = f"5h: {pct5}%  |  7d: {pct7}%"

        if not self.startup_notified:
            self.startup_notified = True
            Notify.Notification.new("✓ Claude Usage Widget Started", f"Current usage: {usage_str}", "dialog-information").show()
            return

        pct_val = int(dominant * 100)
        for threshold, title, msg, icon, urgency in THRESHOLDS:
            if pct_val >= threshold and threshold > self.last_notified_threshold:
                n = Notify.Notification.new(title, f"{usage_str}\n{msg}", icon)
                n.set_urgency(urgency)
                n.show()
                self.last_notified_threshold = threshold
                break

    def _prompt_token(self):
        dialog = Gtk.Dialog(title="Claude OAuth Token")
        dialog.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, Gtk.STOCK_OK, Gtk.ResponseType.OK)
        dialog.set_default_size(450, -1)

        box = dialog.get_content_area()
        box.set_spacing(8)
        box.set_margin_top(12)
        box.set_margin_bottom(12)
        box.set_margin_start(12)
        box.set_margin_end(12)

        label = Gtk.Label()
        label.set_markup(
            "Enter your Claude OAuth token.\n"
            "<small>Get it from <b>~/.claude/.credentials.json</b> (Claude Code)\n"
            "or browser DevTools → Network → api.anthropic.com headers.</small>")
        label.set_line_wrap(True)
        box.pack_start(label, False, False, 0)

        entry = Gtk.Entry()
        entry.set_placeholder_text("sk-ant-oat01-...")
        entry.set_visibility(False)
        box.pack_start(entry, False, False, 0)

        dialog.show_all()
        if dialog.run() == Gtk.ResponseType.OK:
            token = entry.get_text().strip()
            if token:
                self.token = token
                save_token(token)
                self._refresh()
        dialog.destroy()
        return False

    def _quit(self):
        self.running = False
        Notify.uninit()
        Gtk.main_quit()

    def run(self):
        Gtk.main()


if __name__ == "__main__":
    ClaudeUsageApp().run()
