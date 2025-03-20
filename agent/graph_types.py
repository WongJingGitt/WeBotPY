from typing import Any, Dict, List, TypedDict, Literal
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

class PlanResultItem(BaseModel):
    step_id: int = Field(..., description='步骤的唯一标识符，用于标识当前步骤在任务中的顺序和引用。')
    status: Literal["success", "error", "pending"] = Field(..., description='当前步骤的执行结果状态，仅允许三个值：success/error/pending，其中')
    output: Any = Field(..., description='当前步骤的输出结果')
    error: str = Field(default='', description='当前步骤的错误信息，如果步骤执行成功，则该字段为空。如果步骤执行出错，则记录出错信息。')
    clarification: str = Field(default='', description='如若需要用户澄清时，展示给用户的的澄清信息，不需要澄清则为空。')
    user_feedback: str = Field(default='', description='用户对当前步骤的 Clarification 的反馈，用于记录用户对 clarification 的反馈。')
    decision_log: str = Field(default='', description='记录当前步骤的决策日志，用于记录当前步骤的决策过程。')


class PlanResult(BaseModel):
    completed_steps: List[int] = Field(..., description='已完成的步骤的ID列表，用于记录当前任务的执行进度。')
    last_step_id: int = Field(..., description='最后一次执行的步骤ID，在每执行完一个步骤，你都要更新这个字段，以便出错时进行快速重试。')
    result: List[PlanResultItem] = Field(..., description='任务执行结果，用于记录每个步骤的输出结果。')


class PlanModel(BaseModel):
    step_items: List[StepItemModel] = Field(...,
                                            description='步骤列表，包含每个步骤的详细信息。注意：**每个步骤的格式必须为字典。**')


class PlanGenerationError(Exception):
    """自定义的Plan生成错误"""

    def __init__(self, message):
        self.message = message

    def __str__(self):
        return self.message
    
class ExecuteToolError(Exception):
    """自定义的Tool执行错误"""
    def __init__(self, message):
        self.message = message
    
    def __str__(self):
        return self.message


