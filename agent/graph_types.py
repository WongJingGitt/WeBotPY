from typing import Any, Dict, List, TypedDict, Union
from pydantic import BaseModel, Field


class StepItemModel(BaseModel):
    step_id: int = Field(..., description='步骤的唯一标识符，用于标识当前步骤在任务中的顺序和引用。')
    description: str = Field(..., description='对当前步骤的简要描述，显示给用户，帮助理解该步骤的目的和任务。')
    tool: str = Field(..., description='执行该步骤所调用的工具函数名称。')
    input: Dict[str, Any] = Field(default={}, description='调用工具函数时所需要的输入参数，格式为字典。')
    depends_on: List[int] = Field(default=[], description='该步骤依赖的其他步骤的ID列表，用于定义执行顺序和依赖关系。')
    clarification: str = Field(default='', description='当该步骤可能需要用户澄清或确认时，提供相应提示信息。')
    decision_required: str = Field(default='',
                                   description='描述该步骤中可能需要模型推理或任务执行专家进行自主决策的内容。')

    model_config = {"json_schema_extra": {"type": "object"}}


class PlanResult(StepItemModel):
    result: Dict[str, Any] = Field(default={}, description='工具函数的返回结果，格式为字典。')


class PlanModel(BaseModel):
    step_items: List[StepItemModel] = Field(...,
                                            description='步骤列表，包含每个步骤的详细信息。注意：**每个步骤的格式必须为字典。**')


class PlanGenerationError(Exception):
    """自定义的Plan生成错误"""

    def __init__(self, message):
        self.message = message

    def __str__(self):
        return self.message

