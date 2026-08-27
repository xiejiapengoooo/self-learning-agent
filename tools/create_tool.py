import ast
import json
import os
import tempfile
from pathlib import Path


TOOLS_DIR = Path(__file__).resolve().parent
TOOLS_REGISTRY_PATH = TOOLS_DIR / "tools.json"


def _get_json_type(annotation: ast.expr | None) -> str:
    if annotation is None:
        return "any"

    annotation_name = ast.unparse(annotation)
    base_name = annotation_name.rsplit(".", 1)[-1]
    type_mapping = {
        "str": "string",
        "int": "integer",
        "float": "number",
        "bool": "boolean",
        "list": "array",
        "tuple": "array",
        "set": "array",
        "dict": "object",
    }

    if isinstance(annotation, ast.Subscript):
        container_name = ast.unparse(annotation.value).rsplit(".", 1)[-1]
        return type_mapping.get(container_name, annotation_name)

    return type_mapping.get(base_name, annotation_name)


def _write_text_atomically(path: Path, content: str) -> None:
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        delete=False,
    ) as temp_file:
        _ = temp_file.write(content)
        temp_path = Path(temp_file.name)

    try:
        os.replace(temp_path, path)
    finally:
        temp_path.unlink(missing_ok=True)


def create_tool(code: str) -> None:
    if not isinstance(code, str) or not code.strip():
        raise ValueError("code must be a non-empty string")

    try:
        syntax_tree = ast.parse(code)
    except SyntaxError as error:
        raise ValueError("code is not valid Python") from error

    tool_functions = [
        node
        for node in syntax_tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and not node.name.startswith("_")
    ]
    if len(tool_functions) != 1:
        raise ValueError("code must contain exactly one public top-level function")

    tool_function = tool_functions[0]
    tool_name = tool_function.name
    tool_path = TOOLS_DIR / f"{tool_name}.py"
    if tool_path.resolve() == Path(__file__).resolve():
        raise ValueError("create_tool cannot overwrite itself")

    try:
        registry = json.loads(TOOLS_REGISTRY_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError("tools.json is missing or invalid") from error
    if not isinstance(registry, dict):
        raise ValueError("tools.json must contain a JSON object")
    if tool_path.exists() or tool_name in registry:
        raise ValueError(f"tool already exists: {tool_name}")

    positional_args = [
        *tool_function.args.posonlyargs,
        *tool_function.args.args,
        *tool_function.args.kwonlyargs,
    ]
    args = {
        argument.arg: {
            "type": _get_json_type(argument.annotation),
            "description": "",
        }
        for argument in positional_args
        if argument.arg not in {"self", "cls"}
    }
    if tool_function.args.vararg:
        args[tool_function.args.vararg.arg] = {
            "type": "array",
            "description": "",
        }
    if tool_function.args.kwarg:
        args[tool_function.args.kwarg.arg] = {
            "type": "object",
            "description": "",
        }

    registry[tool_name] = {
        "name": tool_name,
        "description": ast.get_docstring(tool_function) or "",
        "args": args,
    }

    _write_text_atomically(tool_path, code)
    try:
        registry_content = json.dumps(registry, ensure_ascii=False, indent=2) + "\n"
        _write_text_atomically(TOOLS_REGISTRY_PATH, registry_content)
    except Exception:
        tool_path.unlink(missing_ok=True)
        raise
