"""
llm.py：模型客户端
单独一个文件的原因：以后三个审查员要共用一个模型配置
改模型名、改温度只改一处
"""
import os

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from pydantic import BaseModel
from app.state import Finding
load_dotenv()


class ReviewResult(BaseModel):
    """包一层的原因见下方说明"""
    findings: list[Finding]

llm=ChatOpenAI(
    model="deepseek-chat",
    base_url="https://api.deepseek.com",
    api_key=os.environ["DEEPSEEK_API_KEY"],
    temperature=0,
    timeout=60
).with_structured_output(ReviewResult,method="function_calling") #把Pydantic类翻译成JSON Schema，塞给模型当填写规范，模型按规范返回JSON，LangChain自动转回对象