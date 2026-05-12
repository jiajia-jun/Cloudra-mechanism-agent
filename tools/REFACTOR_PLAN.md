# tools 模块改造计划

> **目标**：在不改动项目整体框架（Agent / Session / reAct / 目录结构 / 模块加载机制）的前提下，改造 tools 模块的 Schema 体系与 OpenAI Function Calling 接口对接方式。
>
> **核心诉求**（来自 `tools/__init__.py`）：不要把工具描述、参数描述等全部塞进 `description` 里，要让 `input_schema` 能够完美对应 OpenAI 接口的 `parameters` 字段。

---

## 一、现状与问题

### 1.1 OpenAI 接口格式不匹配

当前 `agent.py` 的 `llm_call()` 将工具列表直接传给 OpenAI `tools` 参数，但 `Tool.toJson()` 在基类中返回 `{}`，子类也未正确实现。实际走的是 `tools_class.py` 里的 `get_tools()`，它调用 `tool.toJson()`，结果每个工具序列化出来的格式不符合 OpenAI Function Calling 规范：

```json
{
  "type": "function",
  "function": {
    "name": "tool_name",
    "description": "...",
    "parameters": {
      "type": "object",
      "properties": { ... },
      "required": [ ... ]
    }
  }
}
```

### 1.2 `description` 过度膨胀

以 `PaperSearcher` 为例，`tool_description` 里塞进了：
- 使用权限
- 功能描述
- 使用场景
- 输入格式与每个字段的说明
- 输出格式与每个字段的说明

LLM 的 `description` 应该简洁描述"这个工具是做什么的"，参数细节应该交给 `parameters.properties.xxx.description`。

### 1.3 `input_schema` / `output_schema` 实现粗糙

- 自定义 `__init__(self, json_dict)` 与 Pydantic `BaseModel` 的初始化逻辑冲突。
- 手动维护 `keys` 列表，冗余且易出错。
- `toJson()` 只是简单 dump 属性值，不是 JSON Schema。
- 没有 `from_dict` 类的工厂方法，`reAct.py` 里调用 `tool.input_schema.toClass(tool_args)` 在基类中直接返回类本身，逻辑未真正跑通。

---

## 二、改造阶段

### 阶段 1：Schema 基类重构（`tools_class.py`）

#### 2.1.1 `input_schema` 重新设计

```python
from pydantic import BaseModel, Field
from typing import Any

class input_schema(BaseModel):
    """
    工具输入模式基类。
    子类只需声明字段并用 Field(description="...") 注解即可自动生成 OpenAI parameters。
    """

    @classmethod
    def to_parameters_schema(cls) -> dict:
        """
        生成符合 OpenAI Function Calling 的 parameters 字典。
        基于 Pydantic model_json_schema() 做微调：
        - 注入 Field(description) 到 properties 中
        - 补充 required 列表（无默认值且非 Optional 的字段）
        - 设置 additionalProperties: false
        """
        schema = cls.model_json_schema()
        parameters = {
            "type": "object",
            "properties": schema.get("properties", {}),
            "required": schema.get("required", []),
            "additionalProperties": False,
        }
        return parameters

    @classmethod
    def from_args(cls, arg_dict: dict) -> "input_schema":
        """从 LLM 返回的 arguments dict 构造输入实例。"""
        return cls(**arg_dict)

    def toJson(self) -> dict:
        """实例序列化为 dict，用于日志或上下文回传。"""
        return self.model_dump(mode="json")
```

**关键点**：
- 不再覆盖 `__init__`，完全交给 Pydantic。
- 删除 `keys` 列表，改用 `model_fields` / `model_json_schema()` 自省。
- `to_parameters_schema()` 输出就是 OpenAI 要的 `function.parameters`。

#### 2.1.2 `output_schema` 重新设计

```python
class output_schema(BaseModel):
    """
    工具输出模式基类。
    """

    def toJson(self) -> dict:
        return self.model_dump(mode="json")
```

同样删除 `keys` 和自定义 `__init__`。

#### 2.1.3 `Tool` 基类改造

```python
class Tool(BaseModel):
    tool_id: str
    tool_name: str
    tool_description: str          # 仅保留：一句话功能描述 + 使用场景提示
    input_schema: type[input_schema]   # 类型注解，指向具体的 schema 类
    output_schema: type[output_schema]

    # ... 权限方法保持不变 ...

    def toJson(self) -> dict:
        """
        返回标准 OpenAI function 格式。
        agent.py 里的 get_tools() 可直接使用此输出。
        """
        return {
            "type": "function",
            "function": {
                "name": self.tool_name,
                "description": self.tool_description,
                "parameters": self.input_schema.to_parameters_schema(),
            }
        }

    def toClass(self, arg_dict: dict) -> input_schema:
        """兼容旧接口，供 reAct.py 调用。"""
        return self.input_schema.from_args(arg_dict)
```

---

### 阶段 2：`tools/__init__.py` 补齐

```python
from pathlib import Path
import sys
import pkgutil

CURRENT_DIR = Path(__file__).parent

def to_openai_format(tool: Tool) -> dict:
    """
    将 Tool 实例转换为 OpenAI tools 列表元素。
    直接委托给 tool.toJson()，因为 Tool 基类已实现标准格式。
    """
    return tool.toJson()

def get_tools_lst():
    """保持原有动态加载逻辑不变。"""
    tools = []
    for module_info in pkgutil.iter_modules([str(CURRENT_DIR)]):
        module_name = module_info.name
        if module_name != '__init__':
            __import__(f"{__name__}.{module_name}")
            module = sys.modules[f"{__name__}.{module_name}"]
            tool_class = getattr(module, 'get_class', None)
            if tool_class:
                tools.append(tool_class)
    return tools

get_tools = get_tools_lst()
```

---

### 阶段 3：各工具子模块规范化

改造原则：
1. **`tool_description` 精简**：只保留【功能描述】+【使用场景】，不超过 3~4 句话。
2. **参数说明迁移到 `Field`**：在 `input_schema` 的每个字段上用 `Field(description="...", default=...)` 注解。
3. **删除 `keys` 列表**。
4. **`output_schema` 同样使用 `Field`**。

以 `TextReader` 为例，改造后样板：

```python
from pydantic import Field
from ...tools_class import Tool, input_schema, output_schema
from ...session_class import Session

class TextReader_input_schema(input_schema):
    filepath: str = Field(description="要读取的文件绝对路径")
    start_line: int = Field(default=0, description="起始行号，左闭，从 0 开始")
    end_line: int = Field(default=-1, description="结束行号，左开；-1 表示读到末尾")

class TextReader_output_schema(output_schema):
    content: str = Field(description="读取到的文本内容")

class TextReader(Tool):
    tool_id: str = 't-2'
    tool_name: str = 'text_reader'
    tool_description: str = (
        "以文本形式读取本地文件（md/txt/json/py/sh 等）。"
        "支持指定起始行与结束行进行切片阅读。"
    )
    input_schema: type[input_schema] = TextReader_input_schema
    output_schema: type[output_schema] = TextReader_output_schema

    def is_read(self) -> bool:
        return True

    async def tool_call(self, user_input: TextReader_input_schema, session: Session) -> TextReader_output_schema:
        # ... 原有业务逻辑 ...
        return TextReader_output_schema(content=content_str)

def get_class():
    return TextReader
```

**待改造文件清单**：
- `tools/Bashtool/bashtools.py`
- `tools/Searchtool/paper_searcher.py`
- `tools/Searchtool/pdf2md.py`
- `tools/Searchtool/text_reader.py`
- `tools/Writetool/text_writer.py`
- `tools/Managetool/subagent_launcher.py`

> 注意：`Bashtools` 的 `tool_description` 是动态生成的（根据子 agent 权限拼接可用命令列表），改造时保留动态生成逻辑，但将参数说明（command / timeout / terminal_id）从字符串模板中移除，移到 `Bashtools_input_schema` 的 `Field` 中。

---

### 阶段 4：调用链路微调和兼容

#### 4.1 `tools_class.py` 的 `get_tools()`

```python
def get_tools() -> list[dict]:
    """
    将 tools 模块中的对象加载为 OpenAI 格式的 dict 列表。
    """
    tools = get_tools_lst()
    return [tool.toJson() for tool in tools]
```

这里有一个细节：`get_tools_lst()` 返回的是**类**（如 `TextReader`），不是实例。如果 `Tool` 是 `BaseModel` 子类，类上调用 `toJson()` 需要改成类方法或先实例化。

**建议方案**：
- 让 `Tool.toJson()` 保持为**实例方法**。
- `get_tools()` 中先 `tool()` 实例化（子类无必填字段时可空构造；若子类构造函数有参数如 `Bashtools(subagent)`，则 `get_tools()` 只做静态信息收集，可改用一个无参构造或类方法 `tool.get_schema_json()`）。

更干净的方案：把 OpenAI 格式生成改为**类方法** `tool_schema_json()`，这样不需要实例化即可拿到描述信息：

```python
class Tool(BaseModel):
    @classmethod
    def tool_schema_json(cls) -> dict:
        return {
            "type": "function",
            "function": {
                "name": cls.tool_name,
                "description": cls.tool_description,
                "parameters": cls.input_schema.to_parameters_schema(),
            }
        }
```

然后 `get_tools()` 调用 `tool_class.tool_schema_json()`。实例方法 `toJson()` 可保留用于实例序列化到日志。

#### 4.2 `reAct.py` 的 `act_result()`

当前代码：
```python
input_instance = tool.input_schema.toClass(tool_args)
```

改造后 `toClass()` 内部调用 `self.input_schema.from_args(tool_args)`，即 `cls(**tool_args)`。只要 `input_schema` 是合法的 Pydantic Model，这里就能自动完成类型校验与转换。

需要确认 `tool` 在此处是**实例**还是**类**。如果是类，需改为：
```python
input_instance = tool.input_schema.from_args(tool_args)
```

或保留 `toClass()` 兼容方法。

#### 4.3 `agent.py` 的 `llm_call()`

目前：
```python
tools = self.get_available_tools()
# ...
tools=tools,
```

只要 `get_tools()` 返回的是标准 OpenAI function dict 列表，此处无需改动。

---

## 三、验收标准

1. `get_tools()` 返回的列表可直接作为 `client.chat.completions.create(..., tools=...)` 的参数，不报错。
2. 每个工具的 `tool_description` 长度控制在 200 字以内，不再包含参数细节。
3. OpenAI 返回的 `tool_calls` 中的 `arguments` 能被 `input_schema.from_args()` 正确反序列化，且 Pydantic 自动做类型校验。
4. 所有现有工具的 `tool_call()` 签名、权限判断逻辑、`get_class()` 导出方式均保持不变。
5. `tools/__init__.py` 的模块动态加载机制不变。

---

## 四、风险提示

- **Pydantic v2 兼容性**：项目目前使用的是 Pydantic v2（`model_dump` / `model_json_schema`），计划中的 API 均为 v2 风格。若环境实际为 v1，需将 `model_dump` 替换为 `dict()`，`model_json_schema()` 替换为 `schema()`。
- **`Bashtools` 动态 description**：`Bashtools.__init__` 接收 `subagent` 参数，导致无法无参实例化。建议将静态 schema 信息（`tool_id`, `tool_name`, `tool_description` 模板, `input_schema`）提升为类属性；动态部分（可用命令列表）可在实例化后通过实例属性或单独的 `get_dynamic_description()` 方法提供，但 OpenAI schema 只依赖静态类属性即可。
- **权限过滤时机**：`agent.py` 的 `get_available_tools()` 当前基于 `tool.permission_all()` 做过滤。如果 `Bashtools` 的权限需要结合具体命令判断，而 schema 是静态的，这没有问题——权限过滤只决定 agent 能否"看到"这个工具，具体命令的权限在 `tool_call` 内部再校验。

---

## 五、建议的实施顺序

1. **先改基类**：`tools_class.py` 中的 `input_schema`、`output_schema`、`Tool`。
2. **再改一个最简单的工具做验证**：推荐 `text_reader` 或 `text_writer`，字段少、无动态 description。
3. **跑通 `agent.py` → `llm_call()` → OpenAI 接口**：确认 `tools` 参数不报错。
4. **批量改造剩余工具**。
5. **最后回归测试 `reAct.py` 的 `act_result()`**：确认工具调用链路端到端跑通。
