"""
graph.py:把三个节点装配成一张图
这个文件不含任何业务逻辑，只描述”谁先谁后、连到哪“
"""
from langgraph.constants import START, END
from langgraph.graph import StateGraph

from app.state import ReviewState
from app.nodes.parse import parse_node
from app.nodes.review import review_node
from app.nodes.report import report_node

def build_graph():
    #1:建图
    g=StateGraph(ReviewState)
    #2:添加节点
    g.add_node("parse",parse_node)
    g.add_node("review",review_node)
    g.add_node("report",report_node)
    #3:连线
    g.add_edge(START,"parse")
    g.add_edge("parse","review")
    g.add_edge("review","report")
    g.add_edge("report",END)

    #4:编译：把定义变成能invoke的对象
    return g.compile()

#5:模块级实例
graph=build_graph()