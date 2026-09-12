"""Phase 2 verification gate.

Proves three things about the graph:
  1. all five nodes execute in order;
  2. the cyclic critic -> generator edge actually fires on a real violation;
  3. execution_logs ACCUMULATE across iterations (the operator.add reducer),
     so the rejection history survives to the frontend terminal.

Run:  python -m backend.tests.test_phase2_workflow
"""

from __future__ import annotations

import sys

import numpy as np

from backend.agents import critic_node, generator_node
from backend.agents.logs import render
from backend.agents.workflow import describe_graph, run_simulation
from backend.config import REGIONS, settings
from backend.generator.stub import StubGenerator

INTERVENTION = ("Build 3 series check-dams along the main dry stream bed to "
                "trap monsoon runoff and recharge shallow aquifers.")


def run() -> int:
    print("=" * 78)
    print("PHASE 2 VERIFICATION GATE")
    print("=" * 78)
    print(describe_graph())

    region = REGIONS["anantapur"]
    print(f"\nRegion        : {region.name}")
    print(f"Intervention  : {INTERVENTION}")
    print(f"Retry budget  : {settings.max_critic_iterations}")
    print(f"Critic        : {critic_node.get_critic().name}")

    # Stub deliberately spills water uphill on its first pass, so the critic
    # has a genuine physics violation to catch rather than a faked flag.
    generator_node.set_generator(StubGenerator(simulate_hallucination=True))

    print("\n--- executing graph ---\n")
    final = run_simulation(
        region_id="anantapur",
        intervention_text=INTERVENTION,
        intervention_year=5,
    )

    logs = final["execution_logs"]
    print(render(logs))

    # ---- assertions ----------------------------------------------------
    print("\n--- verification ---")

    iterations = int(final["iteration_count"])
    assert iterations >= 2, (
        f"Cyclic edge never fired: generator ran {iterations}x, expected >=2")
    print(f"[ok] cyclic edge fired: generator ran {iterations} times")

    rejects = [e for e in logs if e["type"] == "reject"]
    assert rejects, "No rejection logged -- the critic never pushed back"
    print(f"[ok] critic rejected {len(rejects)} time(s)")

    # The accumulation proof: an early rejection must still be present in the
    # final log list. With LangGraph's default reducer it would be gone.
    first_reject_step = min(e["step"] for e in rejects)
    last_step = max(e["step"] for e in logs)
    assert first_reject_step < last_step, "Rejection is not followed by later logs"
    assert len(logs) == len({e["step"] for e in logs}), "Log steps not unique"
    assert [e["step"] for e in logs] == sorted(e["step"] for e in logs), \
        "Log steps out of order"
    print(f"[ok] logs accumulated: {len(logs)} entries, steps 1..{last_step}, "
          f"rejection at step {first_reject_step} retained")

    agents_seen = {e["agent"] for e in logs}
    assert len(agents_seen) == 5, f"Expected 5 agents, saw {sorted(agents_seen)}"
    print(f"[ok] all 5 nodes executed: {len(agents_seen)} distinct agents")

    assert final["is_approved"], "Loop did not converge to an approved scene"
    print(f"[ok] converged: approved={final['is_approved']}, "
          f"score={final['plausibility_score']:.0f}%")

    # Geometry sanity.
    mask = final["spatial_change_mask"]
    coords = final["target_stream_coords"]
    assert np.any(mask >= 1.0), "Planner produced no impoundment"
    assert coords, "Planner sited no structures"
    for site in coords:
        assert site["slope_deg"] < 5.0, f"Dam sited on {site['slope_deg']:.1f} deg"
    print(f"[ok] planner sited {len(coords)} dams, all on slope < 5 deg")

    plan = final["intervention_plan"]
    print(f"[ok] parsed intent: {plan['count']}x {plan['structure_type']} "
          f"via {plan['placement_strategy']}")

    # Final scene must be free of the violation that was rejected.
    final_feedback = final["critic_feedback_mask"]
    assert not np.any(final_feedback), \
        f"Approved scene still has {int(np.sum(final_feedback))} violating px"
    print("[ok] approved scene has zero remaining violations")

    print("\nPHASE 2 VERIFIED")
    return 0


def test_phase2_cyclic_loop():
    assert run() == 0


if __name__ == "__main__":
    sys.exit(run())
