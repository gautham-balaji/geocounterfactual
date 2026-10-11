/**
 * Live state of one pipeline run, folded from the stream's events.
 *
 * The server says, after every node, which node runs NEXT (decided by the
 * graph's own routing function) and which generate-and-judge pass is in
 * progress. Deriving "active" from the last log line instead -- as the rail
 * once did -- marks the node that just finished, one step behind the graph.
 *
 * Pure: (state, action) -> state, so every view of the run (the rail, the
 * progress strip, the verdict list) reads one source of truth.
 */

export const PIPELINE_NODES = [
  { id: 'input_handler', label: 'Input Handler', agent: 'Input Handler',
    doing: 'Ingesting Sentinel-2 bands and terrain' },
  { id: 'planner', label: 'Planner', agent: 'Intervention-Planner',
    doing: 'Routing drainage and siting structures' },
  { id: 'dynamics', label: 'Dynamics', agent: 'Eco-Hydrological Dynamics',
    doing: 'Bounding growth and recharge' },
  { id: 'generator', label: 'Generator', agent: 'Generator (Diffusion)',
    doing: 'Synthesising the counterfactual scene' },
  { id: 'critic', label: 'Critic', agent: 'Physical-Plausibility Critic',
    doing: 'Judging the scene against the physical rules' },
];

const NODE_BY_AGENT = Object.fromEntries(
  PIPELINE_NODES.map((n) => [n.agent, n.id]));

export const IDLE_PIPELINE = {
  active: null,          // node id running now, or null
  completed: [],         // node ids that have finished at least once
  pass: 0,               // generate-and-judge pass in progress (0 = none)
  maxIterations: 3,
  verdicts: [],          // one per critic pass, in order
  replay: false,         // true when folded from mock logs, not the server
};

function addCompleted(list, id) {
  return id && !list.includes(id) ? [...list, id] : list;
}

/** A server event: {node, logs, next, pass, max_iterations, verdict?}. */
function applyServerEvent(state, ev) {
  return {
    ...state,
    replay: false,
    active: ev.next ?? null,
    completed: addCompleted(state.completed, ev.node),
    pass: ev.pass ?? state.pass,
    maxIterations: ev.max_iterations ?? state.maxIterations,
    verdicts: ev.verdict ? [...state.verdicts, ev.verdict] : state.verdicts,
  };
}

/**
 * The offline mock replays log lines only. Approximate the same state from
 * them so the view still reads correctly when the backend is down; `replay`
 * lets the view say it is a replay.
 */
function applyMockLogs(state, logs) {
  let next = { ...state, replay: true };
  for (const log of logs) {
    const id = NODE_BY_AGENT[log.agent];
    if (!id) continue;
    if (next.active && next.active !== id) {
      next.completed = addCompleted(next.completed, next.active);
    }
    next.active = id;
    if (id === 'generator' && next.pass === next.verdicts.length) {
      next.pass += 1;
    }
    if (id === 'critic' && (log.type === 'reject' || log.type === 'success')) {
      const rejected = log.type === 'reject';
      next.verdicts = [...next.verdicts, {
        iteration: next.pass || next.verdicts.length + 1,
        outcome: rejected ? 'retry' : 'approved',
        approved: !rejected,
        score: null,
        violations: rejected
          ? [log.text.replace(/^Iteration \d+ rejected:\s*/, '')] : [],
        failed_rules: [],
        evaluated_rules: [],
        feedback_px: 0,
      }];
    }
  }
  return next;
}

export function pipelineReducer(state, action) {
  switch (action.type) {
    case 'reset':
      return IDLE_PIPELINE;
    case 'event': {
      const ev = action.event || {};
      return 'next' in ev ? applyServerEvent(state, ev)
                          : applyMockLogs(state, ev.logs || []);
    }
    case 'finish':
      return { ...state, active: null,
               completed: addCompleted(state.completed, state.active) };
    default:
      return state;
  }
}
