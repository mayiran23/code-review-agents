"""performance审查员：只看性能类问题"""
from app.nodes.base import make_reviewer

performance_node=make_reviewer(category="performance",prompt_file="performance")
