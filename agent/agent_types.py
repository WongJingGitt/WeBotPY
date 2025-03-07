from pydantic import BaseModel, Field
from typing import Literal, Dict, Any, List


class StepItem(BaseModel):
    step_id: int = Field(..., description='步骤的唯一标识符，用于标识当前步骤在任务中的顺序和引用。')
    description: str = Field(..., description='对当前步骤的简要描述，显示给用户，帮助理解该步骤的目的和任务。')
    tool: str = Field(..., description='执行该步骤所调用的工具函数名称。')
    input: Dict[str, Any] = Field(default={}, description='调用工具函数时所需要的输入参数，格式为字典。')
    depends_on: List[int] = Field(default=[], description='该步骤依赖的其他步骤的ID列表，用于定义执行顺序和依赖关系。')
    clarification: str = Field(default='', description='当该步骤可能需要用户澄清或确认时，提供相应提示信息。')
    decision_required: str = Field(default='',
                                   description='描述该步骤中可能需要模型推理或任务执行专家进行自主决策的内容。')

    model_config = {"json_schema_extra": {"type": "object"}}


class PlannerResult(BaseModel):
    status: Literal['IN_PROGRESS', 'COMPLETED', 'NEED_CLARIFICATION'] = Field(default='IN_PROGRESS',
                                                                              description='任务整体状态标识，表示任务当前处于进行中、已完成或需要用户澄清的状态。')
    steps: List[StepItem] = Field(..., description='任务规划师生成的步骤列表，每个步骤定义了任务中的一个具体操作。')

    model_config = {"json_schema_extra": {"type": "object"}}