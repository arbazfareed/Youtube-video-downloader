from __future__ import annotations

import threading
import unittest
import urllib.error
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

from torrent_engine import download_torrent


class TorrentPauseRpcRecoveryTests(unittest.TestCase):
    def test_transient_pause_rpc_disconnect_is_retried(self) -> None:
        process = Mock()
        process.poll.return_value = None
        resume_event = threading.Event()
        resume_event.clear()
        rpc_call = Mock(side_effect=[urllib.error.URLError("temporary disconnect"), None])

        with (
            TemporaryDirectory() as folder,
            patch("torrent_engine._find_aria2", return_value="aria2c"),
            patch("torrent_engine.subprocess.Popen", return_value=process),
            patch("torrent_engine._rpc_port", return_value=45678),
            patch(
                "torrent_engine._find_torrent_status",
                return_value={"gid": "gid", "infoHash": "hash"},
            ),
            patch("torrent_engine._rpc_call", rpc_call),
            patch(
                "torrent_engine._rpc_status",
                return_value={"status": "complete", "files": []},
            ),
            patch("torrent_engine.POLL_INTERVAL", 0),
        ):
            result = download_torrent(
                "magnet:?xt=urn:btih:0123456789abcdef",
                Path(folder),
                threading.Event(),
                lambda *_args: None,
                resume_event=resume_event,
            )

        self.assertEqual(result, str(Path(folder).resolve()))
        self.assertEqual(rpc_call.call_count, 2)
        self.assertEqual(rpc_call.call_args_list[0].args[2], "pause")
        self.assertEqual(rpc_call.call_args_list[1].args[2], "pause")
        process.terminate.assert_called_once_with()

    def test_persistent_pause_rpc_disconnect_fails_after_timeout(self) -> None:
        process = Mock()
        process.poll.return_value = None
        resume_event = threading.Event()
        resume_event.clear()

        with (
            TemporaryDirectory() as folder,
            patch("torrent_engine._find_aria2", return_value="aria2c"),
            patch("torrent_engine.subprocess.Popen", return_value=process),
            patch("torrent_engine._rpc_port", return_value=45678),
            patch(
                "torrent_engine._find_torrent_status",
                return_value={"gid": "gid", "infoHash": "hash"},
            ),
            patch(
                "torrent_engine._rpc_call",
                side_effect=urllib.error.URLError("RPC disconnected"),
            ),
            patch("torrent_engine.RPC_FAILURE_TIMEOUT", 0),
            patch("torrent_engine.POLL_INTERVAL", 0),
        ):
            with self.assertRaisesRegex(RuntimeError, "stopped responding"):
                download_torrent(
                    "magnet:?xt=urn:btih:0123456789abcdef",
                    Path(folder),
                    threading.Event(),
                    lambda *_args: None,
                    resume_event=resume_event,
                )

        process.terminate.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
