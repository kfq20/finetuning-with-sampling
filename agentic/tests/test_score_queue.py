import tempfile
import threading
import time
import unittest
from pathlib import Path
from append_rewrite.terminus.score_queue import fifo_slot
from append_rewrite.terminus.suffix_score import file_slot


def wait_until(predicate):
    end = time.monotonic() + 5
    while not predicate():
        if time.monotonic() > end:
            raise AssertionError('Queue did not reach the expected state')
        time.sleep(0.01)


class ScoreQueueTests(unittest.TestCase):
    def test_fifo_respects_existing_legacy_owner(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            order, threads = [], []
            def worker(index):
                with fifo_slot(root, 1, file_slot) as delay:
                    self.assertGreaterEqual(delay, 0)
                    order.append(index)
                    time.sleep(0.01)
            with file_slot(root, 1):
                for index in range(4):
                    thread = threading.Thread(target=worker, args=(index,))
                    threads.append(thread)
                    thread.start()
                    wait_until(lambda: len(list((root / 'waiting').glob('[0-9]*'))) == index + 1)
                self.assertEqual(order, [])
            for thread in threads:
                thread.join(5)
                self.assertFalse(thread.is_alive())
            self.assertEqual(order, [0, 1, 2, 3])
            self.assertEqual(list((root / 'waiting').glob('[0-9]*')), [])

    def test_stale_waiter_and_exception_release(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'waiting').mkdir()
            (root / 'waiting/00000000000000000000-stale').touch()
            with self.assertRaises(ValueError):
                with fifo_slot(root, 1, file_slot):
                    raise ValueError('failed score transport')
            self.assertEqual(list((root / 'waiting').glob('[0-9]*')), [])
            with fifo_slot(root, 1, file_slot):
                pass


if __name__ == '__main__':
    unittest.main()
