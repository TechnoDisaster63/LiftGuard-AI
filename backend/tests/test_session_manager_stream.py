from app.core.session_manager import SessionManager


def test_only_one_stream_can_drive_a_session():
    manager = SessionManager.__new__(SessionManager)
    import threading
    manager._stream_lock = threading.Lock()

    assert manager.acquire_stream() is True
    assert manager.acquire_stream() is False
    manager.release_stream()
    assert manager.acquire_stream() is True
    manager.release_stream()
