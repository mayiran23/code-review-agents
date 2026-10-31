"""style审查员：只看规范类问题"""
from app.nodes.base import make_reviewer

style_node=make_reviewer(category="style",prompt_file="style")