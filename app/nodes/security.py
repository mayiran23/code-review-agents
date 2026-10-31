"""security审查员，只看安全类问题"""
from app.nodes.base import make_reviewer

security_node=make_reviewer(category="security",prompt_file="security")