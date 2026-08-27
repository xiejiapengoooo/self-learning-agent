# 工具代码生成规范

当现有工具无法完成用户任务、需要调用 `create_tool` 创建新工具时，必须按照以下规范生成 `args.code`。

本规范只约束 `create_tool.args.code` 中的 Python 代码，不改变上层要求的响应格式。最终响应仍需遵循调用方要求，例如：

```json
{"tools": [{"create_tool","args":{"code":"完整的 Python 源代码"}}]}
```

## 必须满足的要求

1. `code` 必须是非空、语法正确、可以被 `ast.parse` 解析的完整 Python 源代码。
2. 代码中必须有且只能有一个公开的顶层函数：
   - 可以使用普通函数 `def` 或异步函数 `async def`。
   - 函数名不能以下划线 `_` 开头。
   - 函数名必须使用有明确含义的 `snake_case` 英文名称。
   - 函数名不能是 `create_tool`。
   - 函数名不能与已有工具重名，否则创建会失败。
3. 如果需要辅助函数，辅助函数名必须以下划线 `_` 开头，例如 `_parse_content`。不要定义第二个公开顶层函数。
4. 公开工具函数必须包含简洁、准确的 docstring。该 docstring 会直接成为 `tools.json` 中的工具描述。
5. 公开工具函数的每个输入参数都必须提供类型注解。优先使用下面列出的内置类型，确保注册信息稳定、易于理解。
6. 建议提供返回类型注解，便于阅读和维护，但当前返回类型不会注册到 `tools.json`。
7. 代码必须包含运行所需的 import、常量和私有辅助函数，不能依赖未定义的变量或上下文。
8. 不要在模块顶层执行实际业务逻辑，不要在 import 时发起网络请求、读写业务文件或修改全局状态。
9. 不要生成测试代码、示例调用、`if __name__ == "__main__"`、`print`、Markdown 代码围栏或代码之外的解释。
10. 优先使用 Python 标准库和项目已有依赖，不要在代码中安装依赖，也不要假设不存在的包、API、环境变量或数据结构。
11. 对无效输入应进行必要校验，并抛出含义明确的异常。不要静默返回错误结果。
12. 返回值应尽量使用字符串、数字、布尔值、列表、字典或 `None` 等易于序列化的值。

## 参数类型注解

`create_tool` 会按照以下规则把参数注解写入 `tools.json`：

| Python 参数注解 | 注册类型 |
| --- | --- |
| `str` | `string` |
| `int` | `integer` |
| `float` | `number` |
| `bool` | `boolean` |
| `list`、`list[T]` | `array` |
| `tuple`、`tuple[T, ...]` | `array` |
| `set`、`set[T]` | `array` |
| `dict`、`dict[K, V]` | `object` |
| 未提供注解 | `any` |
| 其他注解 | 注解的原始文本 |

生成代码时应遵循以下原则：

- 优先使用 `str`、`int`、`float`、`bool`、`list[T]` 和 `dict[K, V]`。
- 除非业务确实需要，否则不要使用 `Any`、`Union`、`Optional`、`Literal`、自定义类或复杂嵌套类型。这些类型不会被转换成标准注册类型，而是以原始注解文本写入注册表。
- 可以设置参数默认值，但默认值和参数是否必填不会写入 `tools.json`，因此不要依赖注册表表达默认值语义。
- 尽量避免 `*args` 和 `**kwargs`。如果使用，前者会注册为 `array`，后者会注册为 `object`。
- 不要把公开工具函数设计成实例方法。名为 `self` 或 `cls` 的参数不会注册到工具参数列表。
- 容器元素类型不会单独写入注册表。例如 `list[float]` 只会注册为 `array`。

## 描述信息

- 工具函数名会同时作为工具文件名和 `tools.json` 的注册键，例如 `fetch_page` 会生成 `fetch_page.py`。
- 工具函数的 docstring 会成为工具的 `description`，因此 docstring 必须描述工具做什么，而不是描述实现过程。
- 当前实现不会从代码中提取每个参数的说明，参数 `description` 会注册为空字符串。参数名本身必须清晰表达含义。

## 推荐代码结构

```python
import math


def _validate_numbers(numbers: list[float]) -> None:
    if not numbers:
        raise ValueError("numbers cannot be empty")
    if not all(math.isfinite(number) for number in numbers):
        raise ValueError("numbers must contain only finite values")


def calculate_average(numbers: list[float]) -> float:
    """计算一组有限数字的平均值。"""
    _validate_numbers(numbers)
    return sum(numbers) / len(numbers)
```

上面的代码符合以下条件：

- 只有 `calculate_average` 一个公开顶层函数。
- 辅助函数 `_validate_numbers` 以下划线开头。
- 输入参数和返回值都有类型注解。
- docstring 可以直接作为工具描述。
- 没有模块导入阶段的副作用。

## 响应示例

当上层要求返回工具调用 JSON 时，应将完整源码正确转义后放入 `args.code`，不要把 Markdown 代码围栏放入 `code`：

```json
{"tools": [{"tool":"create_tool","args":{"code":"def calculate_average(numbers: list[float]) -> float:\n    \"\"\"计算一组数字的平均值。\"\"\"\n    if not numbers:\n        raise ValueError(\"numbers cannot be empty\")\n    return sum(numbers) / len(numbers)\n"}}]}
```

生成完成后，在返回结果前自行检查：Python 语法正确、公开顶层函数数量为一个、函数名不冲突、docstring 存在、所有输入参数都有清晰的类型注解。
