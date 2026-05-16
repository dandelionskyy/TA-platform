"""
Motor controller for two-wheel differential drive robot.
Communicates with Arduino/STM32 MCU via serial/UART.
"""
import logging

logger = logging.getLogger(__name__)

try:
    import serial
    HAS_SERIAL = True
except ImportError:
    HAS_SERIAL = False


class MotorController:
    def __init__(self, port="/dev/ttyUSB0", baudrate=115200):
        self.port = port
        self.baudrate = baudrate
        self._serial = None

        if HAS_SERIAL:
            try:
                self._serial = serial.Serial(port, baudrate, timeout=1)
                logger.info(f"Connected to MCU on {port}")
            except Exception as e:
                logger.warning(f"Serial not available on {port}: {e}")

    def send_command(self, left_speed: int, right_speed: int):
        """
        Send differential drive command.
        left_speed, right_speed: PWM values (-255 to 255)
        """
        cmd = f"M {left_speed} {right_speed}\n"
        if self._serial:
            try:
                self._serial.write(cmd.encode())
                logger.debug(f"Motor cmd: {cmd.strip()}")
            except Exception as e:
                logger.error(f"Serial write error: {e}")
        else:
            logger.info(f"[SIM] Motor: L={left_speed}, R={right_speed}")

    def stop(self):
        self.send_command(0, 0)

    def forward(self, speed: int = 150):
        self.send_command(speed, speed)

    def backward(self, speed: int = 150):
        self.send_command(-speed, -speed)

    def turn_left(self, speed: int = 100):
        self.send_command(-speed, speed)

    def turn_right(self, speed: int = 100):
        self.send_command(speed, -speed)

    def close(self):
        if self._serial:
            self._serial.close()
