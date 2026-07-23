from app.core.security import hash_password, verify_password
from app.routers.ws import robot_key_valid
from app.ai.conversation_memory import ConversationMemory


def test_passwords_are_not_stored_as_plaintext():
    encoded = hash_password("strong-password")
    assert encoded != "strong-password"
    assert verify_password("strong-password", encoded)
    assert not verify_password("wrong-password", encoded)


def test_robot_credentials_are_required():
    assert robot_key_valid("TA-Robot-01", "robot-secret-key-change-me")
    assert not robot_key_valid("TA-Robot-01", "wrong")
    assert not robot_key_valid("unknown", "robot-secret-key-change-me")


def test_context_is_bounded():
    memory = ConversationMemory()
    trimmed = memory._trim([
        {"role": "user", "content": "a" * 20000},
        {"role": "assistant", "content": "b" * 20000},
    ])
    assert sum(len(item["content"]) for item in trimmed) <= 24000
