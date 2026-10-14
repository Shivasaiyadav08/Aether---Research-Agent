
# This is the graph-building file for your Aether Research AI agent. The previous file (nodes.py) defined what each function does. This file decides which function runs next and when the workflow should change direction.
from langgraph.graph import END, START, StateGraph

from app.agents.nodes import make_nodes
from app.agents.state import GraphState


def evidence_route(state: GraphState) -> str:
    return "generate" if state["assessment"]["sufficient"] else "rewrite"


def validation_route(state: GraphState) -> str:
    if not state["valid"] and state["attempts"] <= state["settings"]["max_retries"]:
        return "generate"
    return "finalize"


def next_node(node: str, state: dict) -> str:
    """Checkpoint the same conditional transitions used by the graph."""
    if node == "assess":
        return evidence_route(state)
    if node == "validate":
        return validation_route(state)
    return {"retrieve": "grade", "grade": "assess", "rewrite": "web_search",
            "web_search": "generate", "generate": "validate", "finalize": "end"}[node]


def build_graph(vectors, routing_store=None):
    """One real graph. Conditional edges are driven by the node results."""
    graph = StateGraph(GraphState)
    for name, function in make_nodes(vectors, routing_store).items():
        graph.add_node(name, function)
    graph.add_conditional_edges(START, lambda state: state.get("resume_node", "retrieve"),
                               {name: name for name in make_nodes(vectors, routing_store)})
    graph.add_edge("retrieve", "grade")
    graph.add_edge("grade", "assess")
    graph.add_conditional_edges("assess", evidence_route, {"generate": "generate", "rewrite": "rewrite"})
    graph.add_edge("rewrite", "web_search")
    graph.add_edge("web_search", "generate")
    graph.add_edge("generate", "validate")
    graph.add_conditional_edges(
        "validate", validation_route, {"generate": "generate", "finalize": "finalize"}
    )
    graph.add_edge("finalize", END)
    return graph.compile()
