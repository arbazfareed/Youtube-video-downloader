import ast
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import app_preferences
from app_preferences import PreferencesMixin

V14_ROOT = Path(__file__).resolve().parents[1]


class _ImmediateExecutor:
    def submit(self, fn, *args, **kwargs):
        fn(*args, **kwargs)


class _DeferredRoot:
    """Mimics Tk's root.after(): callbacks run after the calling code has finished."""

    def __init__(self):
        self.pending = []

    def after(self, _delay, callback):
        self.pending.append(callback)

    def run_pending(self):
        callbacks, self.pending = self.pending, []
        for callback in callbacks:
            callback()


class YtdlpUpdateFailureDialogTests(unittest.TestCase):
    def test_failed_update_still_shows_the_error_dialog(self):
        app = PreferencesMixin()
        app.root = _DeferredRoot()
        app.executor = _ImmediateExecutor()
        app.progress_summary = MagicMock()
        app._capture_diagnostic = MagicMock()

        with patch.object(
            app_preferences, "update_ytdlp", side_effect=RuntimeError("pip is unavailable")
        ), patch.object(app_preferences, "messagebox") as messagebox:
            app._update_ytdlp_action()
            # Tk runs the callback only after the except block has exited.
            app.root.run_pending()

        messagebox.showerror.assert_called_once()
        title, text = messagebox.showerror.call_args.args[:2]
        self.assertEqual(title, "yt-dlp update failed")
        self.assertIn("pip is unavailable", text)
        self.assertFalse(app._ytdlp_update_active)


class ExceptionVariableClosureTests(unittest.TestCase):
    """Python deletes `except ... as name` when the block ends.

    A lambda or nested function defined inside the handler and executed later
    (for example through Tk's after()) therefore raises NameError. This guards
    every v14 module against reintroducing that bug.
    """

    def test_no_deferred_callback_uses_the_exception_variable(self):
        offenders = []
        for path in sorted(V14_ROOT.glob("*.py")) + sorted((V14_ROOT / "plugins").glob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for handler in (n for n in ast.walk(tree) if isinstance(n, ast.ExceptHandler) and n.name):
                for inner in ast.walk(handler):
                    if not isinstance(inner, (ast.Lambda, ast.FunctionDef, ast.AsyncFunctionDef)):
                        continue
                    parameters = {argument.arg for argument in inner.args.args}
                    used = {node.id for node in ast.walk(inner) if isinstance(node, ast.Name)}
                    if handler.name in used and handler.name not in parameters:
                        offenders.append(f"{path.name}:{inner.lineno} uses '{handler.name}'")
        self.assertEqual(offenders, [])


if __name__ == "__main__":
    unittest.main()
