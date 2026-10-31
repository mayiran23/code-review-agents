"""
graph.py:把三个节点装配成一张图
这个文件不含任何业务逻辑，只描述”谁先谁后、连到哪“
"""
import sqlite3

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.constants import START, END
from langgraph.graph import StateGraph

from app.nodes.review_gate import review_gate_node
from app.nodes.merge import merge_node
from app.nodes.performance import performance_node
from app.nodes.style import style_node
from app.state import ReviewState
from app.nodes.parse import parse_node
from app.nodes.security import security_node
from app.nodes.report import report_node
#一旦给图装上checkpointer，所有invoke都必须带thread_id，否则直接报错
def build_graph(with_checkpoint: bool = False):
    """建图
    Args:with_checkpoint=False(默认)：评估、批量跑，不需要thread_id
        with_checkpoint=True:    人工确认场景，支持 interrupt 挂起与恢复
    """
    g=StateGraph(ReviewState)
    #2:添加节点
    g.add_node("parse",parse_node)
    g.add_node("security",security_node)
    g.add_node("performance",performance_node)
    g.add_node("style",style_node)
    g.add_node("merge",merge_node)
    g.add_node("review_gate",review_gate_node)
    g.add_node("report",report_node)
    #3:连线
    g.add_edge(START,"parse")
    g.add_edge("parse","security")
    g.add_edge("parse","performance")
    g.add_edge("parse","style")
    g.add_edge("security","merge")
    g.add_edge("performance","merge")
    g.add_edge("style","merge")
    g.add_edge("merge","review_gate")
    g.add_edge("review_gate","report")
    g.add_edge("report",END)

    if with_checkpoint:
        #check_same_thread=False: LangGraph可能在不同线程访问连接
        conn=sqlite3.connect("checkpoints.db",check_same_thread=False)
        return g.compile(checkpointer=SqliteSaver(conn))

    #4:编译：把定义变成能invoke的对象
    return g.compile()

#5:模块级实例
graph=build_graph()