from __future__ import annotations

import importlib
import importlib.util
import pkgutil
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

_EVENTS = {"on_start", "on_progress", "on_complete", "on_error", "on_cancel"}
_plugins: list[tuple[str, dict[str, Any]]] = []
_loaded = False


def _plugin_modules():
    bundled_names = set()
    for module_info in pkgutil.iter_modules(__path__):
        if module_info.name.startswith("_") or module_info.ispkg:
            continue
        bundled_names.add(module_info.name)
        yield module_info.name, None

    if not getattr(sys, "frozen", False):
        return
    external_directory = Path(sys.executable).resolve().parent / "plugins"
    if not external_directory.is_dir():
        return
    for plugin_path in sorted(external_directory.glob("*.py")):
        if plugin_path.stem.startswith("_") or plugin_path.stem in bundled_names:
            continue
        yield plugin_path.stem, plugin_path


def _load_plugin_module(name: str, path: Path | None) -> ModuleType:
    if path is None:
        return importlib.import_module(f"{__name__}.{name}")

    qualified_name = f"{__name__}.{name}"
    spec = importlib.util.spec_from_file_location(qualified_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not create an import loader for {path}.")
    module = importlib.util.module_from_spec(spec)
    sys.modules[qualified_name] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(qualified_name, None)
        raise
    return module


def load_plugins() -> tuple[str, ...]:
    global _loaded
    if _loaded:
        return tuple(name for name, _plugin in _plugins)

    for module_name, plugin_path in _plugin_modules():
        try:
            module = _load_plugin_module(module_name, plugin_path)
            register = getattr(module, "register", None)
            if not callable(register):
                raise TypeError("Plugin must expose a callable register() function.")
            definition = register()
            if not isinstance(definition, dict) or not isinstance(definition.get("name"), str):
                raise TypeError("register() must return a dictionary with a string 'name'.")
            events = definition.get("events")
            if not isinstance(events, dict):
                raise TypeError("Plugin definition must include an 'events' dictionary.")
            unknown = set(events) - _EVENTS
            if unknown:
                raise ValueError(f"Unknown plugin event(s): {', '.join(sorted(unknown))}.")
            if not all(callable(callback) for callback in events.values()):
                raise TypeError("Every plugin event handler must be callable.")
            _plugins.append((definition["name"], events))
        except Exception as error:
            raise RuntimeError(f"Could not load plugin '{module_name}': {error}") from error
    _loaded = True
    return tuple(name for name, _plugin in _plugins)


def emit(event: str, *args: Any) -> Any:
    if event not in _EVENTS:
        raise ValueError(f"Unknown plugin event: {event}")
    load_plugins()
    result = None
    for _name, events in _plugins:
        callback = events.get(event)
        if callback is not None:
            callback_result = callback(*args)
            if event == "on_complete" and callback_result is not None:
                result = callback_result
    return result
