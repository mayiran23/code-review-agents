"""
全系统的共享状态定义
"""
from typing import Literal, TypedDict, Annotated
from operator import add
from pydantic import BaseModel,Field


#1：Finding：单条评审意见
class Finding(BaseModel):
    #文件名（哪个文件）
    file: str=Field(
        description="文件相对路径，例如app/service/order_service.py"
    )
    #从新文件的第几行开始
    start_line: int=Field(
        description="问题所在起始行号（用【新文件】的行号，不是diff里的相对位置）"
    )
    #到第几行结束
    end_line: int=Field(
        description="问题结束行号；单行问题与start_line相同"
    )
    #谁发现的
    #Literal限定取值范围。模型想返回“安全”或者其他都不可以
    #这三个值必须与三个审查节点的名字一一对应，否则归并时会乱
    category: Literal["security","performance","style"]=Field(
        description="由哪个审查员发现，只能是这三个值之一"
    )
    #严重程度
    severity: Literal["P0","P1","P2","P3"]=Field(
        description="严重级别。按rules/severity.yaml的规则表判定，不要凭感觉"
    )
    #什么问题，一句话
    message: str=Field(
        description="问题是什么，一句话说清，不超过80字"
    )
    #怎么改
    suggestion: str | None =Field(
        default=None,
        description="怎么改。给不出具体写法就留空，不要编一个看起来合理的"
    )
    #低于0.6的在报告里单独成段，标注“低置信度，建议人工复核”
    confidence: float = Field(
        default=0.7,
        ge=0.0,
        le=1.0,
        description="你有多大把握这条判断成立，0到1之间"
    )

#2：ReviewState：整条流水线的共享白板
class ReviewState(TypedDict):
    #-----------------输入----------------
    #原始diff文本。parse写入，三个审查节点读取
    patch: str

    #parse解析出的结构化变更
    files: list[dict]

    #---------------审查结果---------------
    findings: Annotated[list[Finding],add]

    #新增merge后的结果，覆盖语义
    merged: list[Finding]

    #两个审查员对同一位置结论矛盾时记在这里
    conflicts: list[dict]

    #-------------决策--------------------
    #route节点写入，条件边读它决定走哪个出口。
    #这三个值必须与条件边函数的返回值严格对应
    decision: Literal["pass","block","need_human"]

    #人工确认时填的理由
    human_note: str | None

    #------------------输出------------------
    #节点生成的最终的Markdown
    report: str
