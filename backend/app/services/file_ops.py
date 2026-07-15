"""Shared synchronization primitives for filesystem mutations."""
from threading import RLock

media_file_operation_lock = RLock()
