"""Privileged runtime. No Qt, camera, network client, or user file operations."""

import argparse
import collections
import os
import pwd
import re
import selectors
import signal
import subprocess
import sys
import time

from evdev import ecodes

from desktop_afk_alert.input_backend import InputCapture
from desktop_afk_alert.protocol import HEARTBEAT_TIMEOUT, MAX_MESSAGE_BYTES, State, decode, encode
from desktop_afk_alert.shortcuts import normalize, validate_shortcut


def self_command() -> list[str]:
    if "__compiled__" in globals():
        return [os.path.realpath(sys.argv[0])]
    return [sys.executable, "-I", "-m", "desktop_afk_alert.helper"]


def session_command(session_id: str) -> list[str]:
    return ["/usr/bin/loginctl", "show-session", session_id, "--no-pager", "-p", "User", "-p", "Active", "-p", "Remote", "-p", "Type", "-p", "Seat", "-p", "LockedHint"]


def session_properties(session_id: str) -> dict[str, str]:
    result = subprocess.run(
        session_command(session_id),
        capture_output=True, timeout=2, check=True, env={"PATH": "/usr/bin:/bin", "LC_ALL": "C"},
    )
    return dict(line.split("=", 1) for line in result.stdout.decode().splitlines() if "=" in line)


class Helper:
    def __init__(self, username: str, uid: int, session_id: str):
        self.username = username
        self.uid = uid
        self.session_id = session_id
        self.selector = selectors.DefaultSelector()
        os.set_blocking(0, False)
        os.set_blocking(1, False)
        self.selector.register(0, selectors.EVENT_READ, ("stdin", None))
        self.capture = None
        self.state = State.IDLE
        self.previous_state = State.IDLE
        self.last_heartbeat = time.monotonic()
        self.last_session_check = 0.0
        self.session_process = None
        self.session_deadline = 0.0
        self.last_status = 0.0
        self.start_deadline = 0.0
        self.shutdown_deadline = None
        self.remaining_shutdown = None
        self.shutdown_requested = False
        self.shutdown_failed = False
        self.shutdown_process = None
        self.auth_process = None
        self.auth_deadline = 0.0
        self.auth_purpose = ""
        self.release_pending = False
        self.settings = None
        self.shortcut = set()
        self.suppressed = set()
        self.buffer = bytearray()
        self.output = collections.deque()
        self.output_bytes = 0
        self.running = True

    def send(self, message_type: str, **values: object) -> None:
        data = encode(message_type, **values)
        self.output.append(data)
        self.output_bytes += len(data)
        if self.output_bytes > 262144:
            raise RuntimeError("The interface stopped reading helper events.")
        self.flush()

    def flush(self) -> None:
        while self.output:
            data = self.output[0]
            try:
                count = os.write(1, data)
            except BlockingIOError:
                return
            self.output_bytes -= count
            if count < len(data):
                self.output[0] = data[count:]
                return
            self.output.popleft()

    def status(self, detail: str = "") -> None:
        remaining = self.remaining_shutdown
        if self.shutdown_deadline is not None:
            remaining = max(0.0, self.shutdown_deadline - time.monotonic())
        self.send("state", state=self.state, previous=self.previous_state,
                  startup_remaining=max(0.0, self.start_deadline - time.monotonic()) if self.state == State.COUNTDOWN else None,
                  shutdown_remaining=remaining, shutdown_requested=self.shutdown_requested, shutdown_failed=self.shutdown_failed,
                  auth_busy=self.auth_process is not None or self.release_pending, detail=detail)

    def check_session(self) -> str:
        properties = session_properties(self.session_id)
        return self.validate_session(properties)

    def validate_session(self, properties: dict[str, str]) -> str:
        if properties.get("User") != str(self.uid) or properties.get("Active") != "yes" or properties.get("Remote") != "no" or properties.get("Type") not in {"x11", "wayland"}:
            raise RuntimeError("Protection requires the user's active local X11 or Wayland session.")
        if properties.get("LockedHint") == "yes":
            raise RuntimeError("The desktop session is locked. Protection has been stopped.")
        seat = properties.get("Seat")
        if not seat:
            raise RuntimeError("The active desktop has no local input seat.")
        return seat

    def poll_session(self, now: float):
        process = self.session_process
        if process is not None:
            if process.poll() is None:
                if now >= self.session_deadline:
                    process.kill()
                    process.wait(timeout=1)
                    raise RuntimeError("Desktop session supervision timed out. Protection has been stopped.")
                return
            output = process.stdout.read(4096).decode()
            process.stdout.close()
            self.session_process = None
            if process.returncode != 0:
                raise RuntimeError("The desktop session is no longer available.")
            properties = dict(line.split("=", 1) for line in output.splitlines() if "=" in line)
            self.validate_session(properties)
        if self.settings is not None and now - self.last_session_check >= 1:
            self.session_process = subprocess.Popen(session_command(self.session_id), stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env={"PATH": "/usr/bin:/bin", "LC_ALL": "C"})
            self.session_deadline = now + 2
            self.last_session_check = now

    def configure(self, message: dict) -> None:
        if self.state != State.IDLE or self.settings is not None:
            raise ValueError("This helper has already been configured.")
        startup = message.get("startup_delay")
        delay = message.get("shutdown_delay")
        enabled = message.get("shutdown_enabled")
        if type(startup) is not int or not 0 <= startup <= 86400 or type(delay) is not int or not 1 <= delay <= 86400 or type(enabled) is not bool:
            raise ValueError("Invalid protection configuration.")
        shortcut = validate_shortcut(message.get("release_shortcut"))
        seat = self.check_session()
        self.capture = InputCapture(self.selector, seat)
        self.settings = {"startup_delay": startup, "shutdown_delay": delay, "shutdown_enabled": enabled}
        self.shortcut = set(shortcut)
        self.send("configured")

    def begin_auth(self, password: str, purpose: str) -> None:
        if self.auth_process is not None or self.release_pending:
            return
        if not isinstance(password, str) or not password or len(password.encode()) > 4096 or "\0" in password:
            self.auth_failed(purpose)
            return
        self.auth_purpose = purpose
        self.auth_process = subprocess.Popen(
            self_command() + ["--auth-worker", self.username],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            env={"PATH": "/usr/bin:/bin", "LC_ALL": "C.UTF-8"},
        )
        os.set_blocking(self.auth_process.stdout.fileno(), False)
        self.auth_process.stdin.write(password.encode())
        self.auth_process.stdin.close()
        self.auth_deadline = time.monotonic() + 30.0
        self.status("Checking password…")

    def auth_failed(self, purpose: str) -> None:
        if purpose == "activate":
            self.send("authentication", success=False, purpose=purpose, message="Password authentication failed. Check your password and account status.")
        else:
            self.restore("Incorrect password. Use the release shortcut to try again.")

    def poll_auth(self) -> None:
        process = self.auth_process
        if process is None:
            return
        if process.poll() is None and time.monotonic() < self.auth_deadline:
            return
        if process.poll() is None:
            process.kill()
            process.wait(timeout=2)
        success = process.returncode == 0 and (process.stdout.read(32) or b"").strip() == b"ok"
        process.stdout.close()
        self.auth_process = None
        if not success:
            self.auth_failed(self.auth_purpose)
            return
        if self.auth_purpose == "activate":
            self.check_session()
            self.state = State.COUNTDOWN
            self.start_deadline = time.monotonic() + self.settings["startup_delay"]
            self.send("authentication", success=True, purpose="activate", message="")
            self.status()
        else:
            self.shutdown_deadline = None
            self.remaining_shutdown = None
            self.release_pending = True
            self.status("Release all keys and buttons to finish.")

    def open_auth(self) -> None:
        self.previous_state = self.state
        if self.shutdown_deadline is not None:
            self.remaining_shutdown = max(0.0, self.shutdown_deadline - time.monotonic())
            self.shutdown_deadline = None
        self.state = State.AUTHENTICATING
        self.suppressed = self.capture.held().copy()
        self.send("authenticate", previous=self.previous_state)
        self.status()

    def restore(self, detail: str = "") -> None:
        self.state = self.previous_state
        self.suppressed = self.capture.held().copy()
        if self.remaining_shutdown is not None and self.state == State.FROZEN and not self.shutdown_requested:
            self.shutdown_deadline = time.monotonic() + self.remaining_shutdown
        self.status(detail)

    def freeze(self, trigger: str) -> None:
        if self.state != State.ARMED:
            return
        self.state = State.FROZEN
        if self.settings["shutdown_enabled"]:
            self.remaining_shutdown = float(self.settings["shutdown_delay"])
            self.shutdown_deadline = time.monotonic() + self.remaining_shutdown
        self.send("incident", trigger=trigger)
        self.status()

    def input_event(self, path: str, event) -> None:
        if event.type == ecodes.EV_SYN and event.code == ecodes.SYN_DROPPED:
            raise RuntimeError("Input synchronization was lost. Protection has been stopped.")
        if self.capture.pointer_click(path, event):
            self.freeze("pointer click")
        if event.type != ecodes.EV_KEY:
            return
        before = self.capture.held()
        was_suppressed = event.code in self.suppressed
        self.capture.update(path, event.code, event.value)
        held = self.capture.held()
        if event.value == 0 and event.code not in held:
            self.suppressed.discard(event.code)
        if event.code in ecodes.KEY:
            typing = self.state == State.AUTHENTICATING and not self.auth_process and not self.release_pending and not was_suppressed and not self.suppressed
            self.send("input", code=event.code, value=event.value, typing=typing, down=event.code in held)
            if event.value == 2:
                return
            normalized = {normalize(code) for code in held if code in ecodes.KEY}
            if event.value == 1 and not self.suppressed and self.state in {State.ARMED, State.FROZEN} and normalized == self.shortcut:
                self.open_auth()
            elif event.value == 0 and event.code in before and not was_suppressed and self.state == State.ARMED:
                self.freeze("keyboard")

    def receive(self, message: dict) -> None:
        kind = message["type"]
        if kind == "heartbeat":
            self.last_heartbeat = time.monotonic()
        elif kind == "configure":
            self.configure(message)
        elif kind == "activate" and self.state == State.IDLE and self.settings is not None:
            self.begin_auth(message.pop("password", ""), "activate")
        elif kind == "authenticate" and self.state == State.AUTHENTICATING:
            self.begin_auth(message.pop("password", ""), "release")
        elif kind == "cancel_auth" and self.state == State.AUTHENTICATING and not self.release_pending:
            self.stop_auth()
            self.restore()
        elif kind == "cancel_countdown" and self.state == State.COUNTDOWN:
            self.running = False
        elif kind == "quit" and self.state == State.IDLE:
            self.running = False
        else:
            raise ValueError("Unexpected helper request.")

    def stop_auth(self) -> None:
        if self.auth_process is not None:
            self.auth_process.kill()
            self.auth_process.wait(timeout=2)
            self.auth_process.stdout.close()
            self.auth_process = None

    def tick(self) -> None:
        now = time.monotonic()
        if now - self.last_heartbeat >= HEARTBEAT_TIMEOUT:
            raise RuntimeError("Interface heartbeat expired. Input devices have been released.")
        if self.capture is not None:
            for code in self.capture.take_removed_keys():
                if code in self.capture.held():
                    continue
                self.suppressed.discard(code)
                if code in ecodes.KEY:
                    self.send("input", code=code, value=0, typing=False, down=False)
        self.poll_session(now)
        self.poll_auth()
        if self.state == State.COUNTDOWN and now >= self.start_deadline:
            if self.capture.grab():
                self.state = State.ARMED
                leds = set()
                for device in self.capture.devices.values():
                    if ecodes.EV_LED in device.capabilities():
                        leds.update(device.leds())
                self.send("keyboard_state", caps_lock=ecodes.LED_CAPSL in leds, num_lock=ecodes.LED_NUML in leds)
                self.send("armed")
                self.status()
        if self.release_pending and not self.capture.held():
            self.capture.release()
            self.release_pending = False
            self.state = State.IDLE
            self.send("authentication", success=True, purpose="release", message="")
            self.status("Protection disabled.")
            self.running = False
        if self.shutdown_deadline is not None and now >= self.shutdown_deadline and not self.shutdown_requested:
            self.shutdown_deadline = None
            self.remaining_shutdown = None
            self.shutdown_requested = True
            try:
                self.shutdown_process = subprocess.Popen(["/usr/bin/systemctl", "poweroff", "--no-block"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env={"PATH": "/usr/bin:/bin", "LC_ALL": "C"})
                self.status("Shutdown requested.")
            except OSError:
                self.shutdown_failed = True
                self.send("error", fatal=False, message="Could not request shutdown. The warning remains active.")
        if self.shutdown_process is not None and self.shutdown_process.poll() is not None:
            if self.shutdown_process.returncode != 0:
                self.shutdown_failed = True
                self.send("error", fatal=False, message="The system rejected the shutdown request. The warning remains active.")
            self.shutdown_process = None
        if now - self.last_status >= 0.25 and self.state != State.IDLE:
            self.status("Release all keys and buttons to arm." if self.state == State.COUNTDOWN and now >= self.start_deadline else "")
            self.last_status = now
        self.flush()

    def run(self) -> int:
        def stop(_signal, _frame):
            self.running = False

        signal.signal(signal.SIGTERM, stop)
        signal.signal(signal.SIGINT, stop)
        signal.signal(signal.SIGHUP, stop)
        self.send("ready")
        try:
            while self.running:
                for key, _mask in self.selector.select(timeout=0.05):
                    category, path = key.data
                    if category == "stdin":
                        data = os.read(0, 8192)
                        if not data:
                            self.running = False
                            break
                        self.buffer.extend(data)
                        while b"\n" in self.buffer:
                            line, _, remainder = self.buffer.partition(b"\n")
                            self.buffer = bytearray(remainder)
                            self.receive(decode(line))
                            line[:] = b"\0" * len(line)
                        if len(self.buffer) > MAX_MESSAGE_BYTES:
                            raise ValueError("Protocol message is too large.")
                    elif category == "udev":
                        self.capture.hotplug()
                    elif category == "input":
                        for event in self.capture.read(path):
                            self.input_event(path, event)
                if self.running:
                    self.tick()
            return 0
        except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
            try:
                self.send("error", fatal=True, message=str(error) if isinstance(error, (ValueError, RuntimeError)) else "A system operation failed. Input devices have been released.")
            except (OSError, RuntimeError):
                pass
            return 1
        finally:
            self.stop_auth()
            if self.session_process is not None:
                if self.session_process.poll() is None:
                    self.session_process.kill()
                self.session_process.wait(timeout=1)
                self.session_process.stdout.close()
            if self.capture is not None:
                self.capture.close()
            self.selector.close()
            self.shutdown_deadline = None
            self.buffer[:] = b"\0" * len(self.buffer)
            try:
                self.flush()
            except OSError:
                pass


def main() -> int:
    parser = argparse.ArgumentParser(description="Desktop AFK Alert privileged helper")
    parser.add_argument("--session")
    parser.add_argument("--auth-worker")
    arguments = parser.parse_args()
    if os.geteuid() != 0:
        print("The helper must be started through sudo by the application.", file=sys.stderr)
        return 1
    if arguments.auth_worker:
        from desktop_afk_alert.pam_auth import authenticate

        password = bytearray(sys.stdin.buffer.read(4097))
        try:
            success = authenticate(arguments.auth_worker, bytes(password))
            print("ok" if success else "denied", flush=True)
            return 0 if success else 1
        finally:
            password[:] = b"\0" * len(password)
    try:
        uid = int(os.environ.get("SUDO_UID", "0"))
        if uid <= 0 or not arguments.session or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", arguments.session):
            raise ValueError("Start the application as your normal desktop user.")
        username = pwd.getpwuid(uid).pw_name
        return Helper(username, uid, arguments.session).run()
    except (KeyError, ValueError, OSError):
        print("Cannot identify the initiating desktop user or session.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
