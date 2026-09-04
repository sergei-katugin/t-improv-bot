import ast
import re
from pathlib import Path


ROOTS = (Path("admin_bot"), Path("public_bot"))


def _sources():
    return [(path, path.read_text()) for root in ROOTS for path in root.rglob("*.py")]


def _decorators() -> str:
    rendered = []
    for path, source in _sources():
        tree = ast.parse(source, filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                rendered.extend(ast.unparse(item) for item in node.decorator_list)
    return "\n".join(rendered)


def test_every_literal_callback_button_has_a_handler():
    decorators = _decorators()
    callbacks = set()
    for path, source in _sources():
        tree = ast.parse(source, filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.keyword) or node.arg != "callback_data":
                continue
            if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                callbacks.add(node.value.value)

    def handled(value: str) -> bool:
        if repr(value) in decorators or f'"{value}"' in decorators:
            return True
        prefix = value.split(":", 1)[0] + ":" if ":" in value else None
        return bool(prefix and (repr(prefix) in decorators or f'"{prefix}"' in decorators))

    missing = sorted(value for value in callbacks if not handled(value))
    assert not missing, f"Callback buttons without handlers: {missing}"


def test_every_callback_data_type_used_by_a_button_has_a_filter():
    all_source = "\n".join(source for _, source in _sources())
    packed_types = set(re.findall(r"\b([A-Z][A-Za-z0-9_]*Cb)\([^\n]*?\)\.pack\(\)", all_source))
    missing = sorted(name for name in packed_types if f"{name}.filter(" not in all_source)
    assert not missing, f"Typed callback buttons without handlers: {missing}"


def test_every_reply_keyboard_button_has_a_message_handler():
    decorators = _decorators()
    labels = set()
    for path, source in _sources():
        if "keyboards/reply.py" not in str(path):
            continue
        tree = ast.parse(source, filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "KeyboardButton":
                # Native Telegram selectors return service messages instead of
                # their visible text; web_app buttons open client-side.
                if any(keyword.arg in {
                    "request_chat", "request_users", "request_contact", "request_location", "web_app",
                } for keyword in node.keywords):
                    continue
                for keyword in node.keywords:
                    if keyword.arg == "text" and isinstance(keyword.value, ast.Constant):
                        labels.add(keyword.value.value)
    missing = sorted(label for label in labels if repr(label) not in decorators and f'"{label}"' not in decorators)
    assert not missing, f"Reply buttons without message handlers: {missing}"
