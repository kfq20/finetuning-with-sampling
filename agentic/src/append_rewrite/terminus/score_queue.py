"""FIFO admission over existing process-owned scoring locks.

Only waiting order changes. Legacy active slots and grandfathered workers remain
owned by their original allocator. Tickets are ephemeral locked files: crashed
waiters can be reaped without trusting a stale PID or an elapsed-time lease.
"""
from contextlib import contextmanager, ExitStack
import fcntl
from pathlib import Path
import time
import uuid


@contextmanager
def fifo_slot(root, capacity, allocator):
    if not root:
        with allocator(root, capacity):
            yield 0.0
        return
    root = Path(root)
    waiting = root / 'waiting'
    waiting.mkdir(parents=True, exist_ok=True, mode=0o700)
    started = time.monotonic()
    ticket = waiting / (f'{time.monotonic_ns():020d}-' + uuid.uuid4().hex)
    hidden = waiting / ('.' + ticket.name)
    owner = hidden.open('x+')
    fcntl.flock(owner, fcntl.LOCK_EX)
    hidden.rename(ticket)  # Publish only after the ownership lock is held.
    try:
        while True:
            with ExitStack() as slot:
                acquired = False
                with (waiting / '.gate').open('a+') as gate:
                    fcntl.flock(gate, fcntl.LOCK_EX)
                    pending = []
                    for path in sorted(waiting.glob('[0-9]*')):
                        try:
                            with path.open('r+') as other:
                                try:
                                    fcntl.flock(other, fcntl.LOCK_EX | fcntl.LOCK_NB)
                                except BlockingIOError:
                                    pending.append(path)
                                else:
                                    path.unlink()  # No live waiter owns this ticket.
                        except FileNotFoundError:
                            pass
                    if pending and pending[0] == ticket:
                        # Waiting here retains FIFO order. Existing scorers need
                        # no gate to release their independent legacy slot locks.
                        slot.enter_context(allocator(root, capacity))
                        ticket.unlink()
                        acquired = True
                if acquired:
                    yield time.monotonic() - started
                    return
            time.sleep(0.05)
    finally:
        ticket.unlink(missing_ok=True)
        owner.close()
