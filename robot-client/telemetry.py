"""
Battery voltage and status telemetry for the TA robot.
Supports both real Raspberry Pi GPIO/ADC and simulation mode.
"""
import random
import time

try:
    import RPi.GPIO as GPIO
    HAS_GPIO = True
except ImportError:
    HAS_GPIO = False


class TelemetryReader:
    def __init__(self):
        self.status = "standby"
        self._battery = 100.0
        self._pos_x = 0.0
        self._pos_y = 0.0
        self._last_battery_read = time.time()

        if HAS_GPIO:
            # Setup ADC for battery reading
            # GPIO.setmode(GPIO.BCM)
            pass

    def _read_battery(self) -> int:
        """Read battery percentage. Uses ADC on real hardware, simulates otherwise."""
        if HAS_GPIO:
            try:
                # TODO: Read from actual ADC (e.g., MCP3008)
                # For now, simulate with slow drain
                pass
            except Exception:
                pass

        # Simulation: slow battery drain + occasional recharge
        elapsed = time.time() - self._last_battery_read
        self._battery -= elapsed * 0.001  # ~0.1% per 100 seconds
        if self._battery < 5:
            self._battery = 100  # Simulate recharge
        self._last_battery_read = time.time()
        return max(0, min(100, int(self._battery)))

    def read(self) -> dict:
        """Read all telemetry data. Called every 2 seconds."""
        return {
            "battery": self._read_battery(),
            "status": self.status,
            "position_x": round(self._pos_x, 2),
            "position_y": round(self._pos_y, 2),
            "position_label": "Library, 2F",
            "timestamp": time.time(),
        }

    def set_status(self, status: str):
        self.status = status

    def update_position(self, dx: float, dy: float):
        """Update position from odometry (called by motor controller)."""
        self._pos_x += dx
        self._pos_y += dy
