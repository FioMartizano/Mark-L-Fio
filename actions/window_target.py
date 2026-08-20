"""
Shared window targeting and verification for JARVIS.

Windows:
    - Finds windows by title fragment
    - Brings the requested window to the foreground
    - Verifies the foreground window
    - Verifies that a target window exists / disappeared

Other platforms:
    - Provides a basic fallback through existing focus mechanisms
"""

import ctypes
import platform
import time
from ctypes import wintypes


_OS = platform.system()


# ─────────────────────────────────────────────────────────────
# Windows helpers
# ─────────────────────────────────────────────────────────────

if _OS == "Windows":

    user32 = ctypes.windll.user32

    EnumWindowsProc = ctypes.WINFUNCTYPE(
        wintypes.BOOL,
        wintypes.HWND,
        wintypes.LPARAM,
    )

    def _get_window_title(hwnd):
        length = user32.GetWindowTextLengthW(hwnd)

        if length <= 0:
            return ""

        buffer = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buffer, length + 1)

        return buffer.value

    def _get_process_name(hwnd):
        """Return the executable name associated with a window."""
        process_id = wintypes.DWORD()

        user32.GetWindowThreadProcessId(
            hwnd,
            ctypes.byref(process_id)
        )

        if not process_id.value:
            return ""

        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

        handle = ctypes.windll.kernel32.OpenProcess(
            PROCESS_QUERY_LIMITED_INFORMATION,
            False,
            process_id.value,
        )

        if not handle:
            return ""

        try:
            buffer = ctypes.create_unicode_buffer(260)
            size = wintypes.DWORD(len(buffer))

            if ctypes.windll.kernel32.QueryFullProcessImageNameW(
                handle,
                0,
                buffer,
                ctypes.byref(size),
            ):
                return buffer.value.rsplit("\\", 1)[-1]

            return ""

        finally:
            ctypes.windll.kernel32.CloseHandle(handle)

    def _is_visible(hwnd):
        return bool(user32.IsWindowVisible(hwnd))

    def _find_windows_windows(target):
        """
        Find visible top-level windows whose title contains target.
        Case-insensitive.
        """
        target = str(target or "").strip().lower()

        if not target:
            return []

        matches = []

        @EnumWindowsProc
        def callback(hwnd, lparam):
            if not _is_visible(hwnd):
                return True

            title = _get_window_title(hwnd)

            if title and target in title.lower():
                matches.append((hwnd, title))

            return True

        user32.EnumWindows(callback, 0)

        return matches

    def _get_foreground_title():
        hwnd = user32.GetForegroundWindow()

        if not hwnd:
            return ""

        return _get_window_title(hwnd)

    def _get_foreground_hwnd():
        return user32.GetForegroundWindow()

    def get_foreground_window_info():
        """
        Return information about the currently focused window.

        Returns:
            {
                "hwnd": hwnd,
                "title": "...",
                "process": "..."
            }

        or None if no foreground window exists.
        """
        hwnd = _get_foreground_hwnd()

        if not hwnd:
            return None

        return {
            "hwnd": hwnd,
            "title": _get_window_title(hwnd),
            "process": _get_process_name(hwnd),
        }

    def is_confirmation_dialog(info):
        """
        Determine whether the foreground window appears to be
        a confirmation or save-changes dialog.

        This is intentionally conservative:
        it only identifies likely dialogs and does not click anything.
        """
        if not info:
            return False

        title = (info.get("title") or "").lower()

        confirmation_keywords = (
            "save changes",
            "save changes?",
            "do you want to save",
            "are you sure",
            "confirm",
            "confirmation",
            "unsaved",
            "save",
        )

        return any(keyword in title for keyword in confirmation_keywords)

    def describe_foreground_window():
        """
        Return diagnostic information about the current foreground window.
        Used while developing confirmation-dialog handling.
        """
        info = get_foreground_window_info()

        if not info:
            return "No foreground window detected."

        return (
            f"Foreground window: {info.get('title') or '(no title)'} | "
            f"Process: {info.get('process') or '(unknown)'} | "
            f"Confirmation dialog: {is_confirmation_dialog(info)}"
        )

    def _focus_hwnd(hwnd):
        """
        Bring a specific window to the foreground.
        """
        if not hwnd:
            return False

        # Restore if minimized.
        SW_RESTORE = 9
        user32.ShowWindow(hwnd, SW_RESTORE)

        result = user32.SetForegroundWindow(hwnd)

        if result:
            return True

        # Fallback: temporarily attach to the foreground thread.
        foreground = user32.GetForegroundWindow()

        if foreground and foreground != hwnd:
            current_thread = user32.GetWindowThreadProcessId(hwnd, None)
            foreground_thread = user32.GetWindowThreadProcessId(
                foreground, None
            )

            attached = False

            try:
                if current_thread != foreground_thread:
                    attached = bool(
                        user32.AttachThreadInput(
                            foreground_thread,
                            current_thread,
                            True,
                        )
                    )

                result = bool(user32.SetForegroundWindow(hwnd))

            finally:
                if attached:
                    user32.AttachThreadInput(
                        foreground_thread,
                        current_thread,
                        False,
                    )

        return result

    def find_target_window(target):
        """
        Find a target window using two levels of matching:

        1. Window title match
        2. Application/process name fallback

        Returns:
            {"hwnd": ..., "title": "..."}
        or None.
        """
        target = str(target or "").strip()

        if not target:
            return None

        target_lower = target.lower()

        # ─────────────────────────────────────────────────────────
        # 1. Try window-title matching first
        # ─────────────────────────────────────────────────────────

        matches = _find_windows_windows(target)

        if matches:
            # Prefer an exact title match.
            for hwnd, title in matches:
                if title.lower() == target_lower:
                    return {
                        "hwnd": hwnd,
                        "title": title,
                    }

            # Otherwise use the first partial title match.
            hwnd, title = matches[0]

            return {
                "hwnd": hwnd,
                "title": title,
            }

        # ─────────────────────────────────────────────────────────
        # 2. Fall back to application/process matching
        # ─────────────────────────────────────────────────────────

        @EnumWindowsProc
        def callback(hwnd, lparam):
            if not _is_visible(hwnd):
                return True

            process_name = _get_process_name(hwnd).lower()

            if not process_name:
                return True

            # Remove .exe for easier comparison.
            executable = process_name.removesuffix(".exe")

            # Match:
            #   "Notion" → "Notion.exe"
            #   "Microsoft Edge" → "msedge.exe" won't match yet
            #
            # Exact executable-name matching is handled here.
            if executable == target_lower:
                matches.append(
                    (hwnd, _get_window_title(hwnd))
                )

            return True

        # Reuse the existing list.
        matches = []

        user32.EnumWindows(callback, 0)

        if matches:
            hwnd, title = matches[0]

            return {
                "hwnd": hwnd,
                "title": title,
            }

        return None

    def focus_target_window(target, timeout=2.0):
        """
        Find and focus a target window.

        Returns:
            (True, actual_title)
            (False, error_message)
        """
        target_window = find_target_window(target)

        if not target_window:
            return False, f"Target window not found: {target}"

        hwnd = target_window["hwnd"]
        title = target_window["title"]

        if not _focus_hwnd(hwnd):
            return False, f"Could not focus target window: {title}"

        deadline = time.monotonic() + timeout

        while time.monotonic() < deadline:
            foreground = _get_foreground_hwnd()

            if foreground == hwnd:
                return True, title

            time.sleep(0.05)

        # Final title-based verification.
        foreground_title = _get_foreground_title()

        if title.lower() == foreground_title.lower():
            return True, title

        return (
            False,
            f"Target focus could not be verified. "
            f"Requested: {title}; foreground: {foreground_title or '(none)'}"
        )

    def target_exists(target):
        return bool(_find_windows_windows(target))

    def target_closed(target, timeout=2.0):
        deadline = time.monotonic() + timeout

        while time.monotonic() < deadline:
            if not target_exists(target):
                return True

            time.sleep(0.1)

        return not target_exists(target)

else:

    # Basic fallback for non-Windows systems.
    # The current project primarily targets Windows.

    def find_target_window(target):
        return None

    def focus_target_window(target, timeout=2.0):
        return (
            False,
            f"Targeted window control is not implemented for {_OS}."
        )

    def target_exists(target):
        return False

    def target_closed(target, timeout=2.0):
        return True