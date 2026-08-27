import ast
import json
import os
import tempfile
from pathlib import Path


TOOLS_DIR = Path(__file__).resolve().parent
TOOLS_REGISTRY_PATH = TOOLS_DIR / "tools.json"


def _get_json_type(annotation: ast.expr | None) -> str:
    if annotation is None:
        raise ValueError("all public function parameters must have type annotations")

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
        if container_name not in type_mapping:
            raise ValueError(f"unsupported parameter annotation: {annotation_name}")
        return type_mapping[container_name]

    if base_name not in type_mapping:
        raise ValueError(f"unsupported parameter annotation: {annotation_name}")
    return type_mapping[base_name]


def _get_function_args(
    tool_function: ast.FunctionDef | ast.AsyncFunctionDef,
) -> dict[str, str]:
    positional_args = [
        *tool_function.args.posonlyargs,
        *tool_function.args.args,
        *tool_function.args.kwonlyargs,
    ]
    args = {
        argument.arg: _get_json_type(argument.annotation)
        for argument in positional_args
        if argument.arg not in {"self", "cls"}
    }
    if tool_function.args.vararg:
        args[tool_function.args.vararg.arg] = "array"
    if tool_function.args.kwarg:
        args[tool_function.args.kwarg.arg] = "object"

    return args


def _validate_registry(
    tool_function: ast.FunctionDef | ast.AsyncFunctionDef,
    registry: dict[str, object],
) -> dict[str, object]:
    required_fields = {"tool_name", "tool_description", "args"}
    registry_fields = set(registry)
    if registry_fields != required_fields:
        missing_fields = required_fields - registry_fields
        unexpected_fields = registry_fields - required_fields
        details = []
        if missing_fields:
            details.append(f"missing: {', '.join(sorted(missing_fields))}")
        if unexpected_fields:
            details.append(
                "unexpected: "
                + ", ".join(sorted(repr(field) for field in unexpected_fields))
            )
        raise ValueError("registry fields do not match: " + "; ".join(details))

    tool_name = registry["tool_name"]
    if not isinstance(tool_name, str) or not tool_name:
        raise ValueError("registry.tool_name must be a non-empty string")
    if tool_name != tool_function.name:
        raise ValueError(
            "registry.tool_name must match the public function name: "
            f"{tool_function.name}"
        )

    tool_description = registry["tool_description"]
    if not isinstance(tool_description, str) or not tool_description.strip():
        raise ValueError("registry.tool_description must be a non-empty string")

    registry_args = registry["args"]
    if not isinstance(registry_args, dict):
        raise ValueError("registry.args must be an object")

    expected_args = _get_function_args(tool_function)
    expected_arg_names = set(expected_args)
    registry_arg_names = set(registry_args)
    if registry_arg_names != expected_arg_names:
        missing_args = expected_arg_names - registry_arg_names
        unexpected_args = registry_arg_names - expected_arg_names
        details = []
        if missing_args:
            details.append(f"missing: {', '.join(sorted(missing_args))}")
        if unexpected_args:
            details.append(
                "unexpected: "
                + ", ".join(sorted(repr(arg) for arg in unexpected_args))
            )
        raise ValueError(
            "registry.args do not match function parameters: " + "; ".join(details)
        )

    normalized_args = {}
    for arg_name, expected_type in expected_args.items():
        arg_registry = registry_args[arg_name]
        if not isinstance(arg_registry, dict):
            raise ValueError(f"registry.args.{arg_name} must be an object")
        if set(arg_registry) != {"type", "description"}:
            raise ValueError(
                f"registry.args.{arg_name} must contain exactly type and description"
            )

        arg_type = arg_registry["type"]
        if arg_type != expected_type:
            raise ValueError(
                f"registry.args.{arg_name}.type must match the function annotation: "
                f"{expected_type}"
            )

        arg_description = arg_registry["description"]
        if not isinstance(arg_description, str) or not arg_description.strip():
            raise ValueError(
                f"registry.args.{arg_name}.description must be a non-empty string"
            )

        normalized_args[arg_name] = {
            "type": arg_type,
            "description": arg_description.strip(),
        }

    return {
        "type": "function",
        "function": {
            "name": tool_function.name,
            "description": tool_description.strip(),
            "parameters": {
                "type": "object",
                "properties": normalized_args,
                "required": list(normalized_args),
                "additionalProperties": False,
            },
        },
    }


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


def create_tool(code: str, registry: dict[str, object]) -> None:
    if not isinstance(code, str) or not code.strip():
        raise ValueError("code must be a non-empty string")
    if not isinstance(registry, dict):
        raise ValueError("registry must be an object")

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
    tool_registry = _validate_registry(tool_function, registry)
    tool_path = TOOLS_DIR / f"{tool_name}.py"
    if tool_path.resolve() == Path(__file__).resolve():
        raise ValueError("create_tool cannot overwrite itself")

    try:
        tools_registry = json.loads(TOOLS_REGISTRY_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError("tools.json is missing or invalid") from error
    if not isinstance(tools_registry, list):
        raise ValueError("tools.json must contain a JSON array")

    registered_tool_names = set()
    for index, tool_definition in enumerate(tools_registry):
        if not isinstance(tool_definition, dict):
            raise ValueError(f"tools[{index}] must be an object")
        function = tool_definition.get("function")
        if (
            tool_definition.get("type") != "function"
            or not isinstance(function, dict)
            or not isinstance(function.get("name"), str)
        ):
            raise ValueError(f"tools[{index}] is not a valid function tool")
        registered_tool_name = function["name"]
        if registered_tool_name in registered_tool_names:
            raise ValueError(f"duplicate tool name in tools.json: {registered_tool_name}")
        registered_tool_names.add(registered_tool_name)

    if tool_path.exists() or tool_name in registered_tool_names:
        raise ValueError(f"tool already exists: {tool_name}")

    tools_registry.append(tool_registry)

    _write_text_atomically(tool_path, code)
    try:
        registry_content = (
            json.dumps(tools_registry, ensure_ascii=False, indent=2) + "\n"
        )
        _write_text_atomically(TOOLS_REGISTRY_PATH, registry_content)
    except Exception:
        tool_path.unlink(missing_ok=True)
        raise
