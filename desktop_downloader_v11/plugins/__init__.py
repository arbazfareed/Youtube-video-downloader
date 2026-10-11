from __future__ import annotations

import importlib
import pkgutil
from types import ModuleType
from typing import Any

_EVENTS = {"on_start", "on_progress", "on_complete", "on_error", "on_cancel"}
_plugins: list[tuple[str, dict[str, Any]]] = []
_loaded = False


def load_plugins() -> tuple[str, ...]:
    global _loaded
    if _loaded:
        return tuple(name for name, _plugin in _plugins)

    for module_info in pkgutil.iter_modules(__path__):
        if module_info.name.startswith("_") or module_info.ispkg:
            continue
        try:
            module: ModuleType = importlib.import_module(f"{__name__}.{module_info.name}")
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
            raise RuntimeError(f"Could not load plugin '{module_info.name}': {error}") from error
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
