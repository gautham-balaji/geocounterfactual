"""LangGraph assembly: the five-node pipeline and the cyclic critic edge.

    START -> input_handler -> planner -> dynamics -> generator -> critic
                                                        ^           |
                                                        |           v
                                                        +--- [violations?] ---> END

No checkpointer is attached. State channels carry raw numpy rasters (per spec
3.1), which a serialising checkpointer cannot persist; runs are therefore
in-memory and non-resumable, which is the right trade for a synchronous
simulation request.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from langgraph.graph import END, START, StateGraph

from backend.agents.critic_node import critic_node
from backend.agents.dynamics import dynamics_node
from backend.agents.generator_node import generator_node
from backend.agents.input_handler import input_handler_node
from backend.agents.planner import planner_node
from backend.agents.state import GeoCounterfactualState, initial_state
from backend.config import settings

logger = logging.getLogger(__name__)

NODE_INPUT = "input_handler"
NODE_PLANNER = "planner"
NODE_DYNAMICS = "dynamics"
NODE_GENERATOR = "generator"
NODE_CRITIC = "critic"


def check_critic_decision(state: GeoCounterfactualState) -> str:
    """Cyclic conditional edge (spec 3.3).

    Three outcomes:
      * approved            -> emit
      * rejected, budget left -> back to the generator with a feedback mask
      * rejected, budget spent -> emit anyway, still flagged unapproved
    """
    if state.get("is_approved"):
        return "approved_output"
    if int(state.get("iteration_count", 0)) >= settings.max_critic_iterations:
        logger.warning("Critic retry budget exhausted; releasing best effort.")
        return "approved_output"
    return "generator_node"


def build_workflow(compiled: bool = True):
    """Wire the five nodes and the feedback loop."""
    graph = StateGraph(GeoCounterfactualState)

    graph.add_node(NODE_INPUT, input_handler_node)
    graph.add_node(NODE_PLANNER, planner_node)
    graph.add_node(NODE_DYNAMICS, dynamics_node)
    graph.add_node(NODE_GENERATOR, generator_node)
    graph.add_node(NODE_CRITIC, critic_node)

    graph.add_edge(START, NODE_INPUT)
    graph.add_edge(NODE_INPUT, NODE_PLANNER)
    graph.add_edge(NODE_PLANNER, NODE_DYNAMICS)
    graph.add_edge(NODE_DYNAMICS, NODE_GENERATOR)
    graph.add_edge(NODE_GENERATOR, NODE_CRITIC)

    graph.add_conditional_edges(
        NODE_CRITIC,
        check_critic_decision,
        {
            "approved_output": END,
            "generator_node": NODE_GENERATOR,   # <-- the feedback loop
        },
    )

    return graph.compile() if compiled else graph


_workflow = None


def get_workflow():
    global _workflow
    if _workflow is None:
        _workflow = build_workflow()
    return _workflow


def run_simulation(
    region_id: str,
    intervention_text: str,
    intervention_year: int = 5,
    bbox: Optional[List[float]] = None,
    recursion_limit: int = 40,
) -> GeoCounterfactualState:
    """Execute the full pipeline synchronously and return the final state."""
    from backend.config import REGIONS

    region = REGIONS.get(region_id)
    seed = initial_state(
        region_id=region_id,
        bbox=bbox or (region.bbox if region else []),
        intervention_text=intervention_text,
        intervention_year=intervention_year,
    )
    return get_workflow().invoke(seed, config={"recursion_limit": recursion_limit})


def stream_simulation(
    region_id: str,
    intervention_text: str,
    intervention_year: int = 5,
    bbox: Optional[List[float]] = None,
    recursion_limit: int = 40,
):
    """Yield (node_name, update) as each node completes.

    Phase 5's SSE endpoint drives the frontend terminal from this.
    """
    from backend.config import REGIONS

    region = REGIONS.get(region_id)
    seed = initial_state(
        region_id=region_id,
        bbox=bbox or (region.bbox if region else []),
        intervention_text=intervention_text,
        intervention_year=intervention_year,
    )
    for chunk in get_workflow().stream(seed,
                                       config={"recursion_limit": recursion_limit}):
        for node_name, update in chunk.items():
            yield node_name, update


def describe_graph() -> str:
    """ASCII topology, for logs and the methodology view."""
    return (
        "START -> input_handler -> planner -> dynamics -> generator -> critic\n"
        "                                                    ^          |\n"
        "                                                    |          v\n"
        "                                     [violations & budget left]\n"
        "                                                    |          |\n"
        "                                                    +----------+ -> END"
    )
