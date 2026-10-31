"""
graph.py:把三个节点装配成一张图
这个文件不含任何业务逻辑，只描述”谁先谁后、连到哪“
"""
from langgraph.constants import START, END
from langgraph.graph import StateGraph

from app.nodes.merge import merge_node
from app.nodes.performance import performance_node
from app.nodes.style import style_node
from app.state import ReviewState
from app.nodes.parse import parse_node
from app.nodes.security import security_node
from app.nodes.report import report_node

def build_graph():
    #1:建图
    g=StateGraph(ReviewState)
    #2:添加节点
    g.add_node("parse",parse_node)
    g.add_node("security",security_node)
    g.add_node("performance",performance_node)
    g.add_node("style",style_node)
    g.add_node("merge",merge_node)
    g.add_node("report",report_node)
    #3:连线
    g.add_edge(START,"parse")
    g.add_edge("parse","security")
    g.add_edge("parse","performance")
    g.add_edge("parse","style")
    g.add_edge("security","merge")
    g.add_edge("performance","merge")
    g.add_edge("style","merge")
    g.add_edge("merge","report")
    g.add_edge("report",END)

    #4:编译：把定义变成能invoke的对象
    return g.compile()

#5:模块级实例
graph=build_graph()