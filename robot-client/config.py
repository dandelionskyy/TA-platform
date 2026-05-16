import os

# Server WebSocket URL (wss:// in production, ws:// in development)
SERVER_URL = os.environ.get("ROBOT_SERVER_URL", "ws://localhost:8000")

# Robot identity
ROBOT_ID = os.environ.get("ROBOT_ID", "TA-Robot-01")

# Auth key for the robot (set on server side too)
AUTH_KEY = os.environ.get("ROBOT_AUTH_KEY", "robot-secret-key-change-me")

# Audio settings
MIC_SAMPLE_RATE = 16000
MIC_CHANNELS = 1
MIC_CHUNK_SIZE = 1024

# Telemetry pins (BCM numbering on Raspberry Pi)
BATTERY_ADC_PIN = 4  # Example: ADC channel for battery voltage
