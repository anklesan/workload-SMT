"""
Makespan minimization workflow scheduler using Z3 SMT solver.
"""

from z3 import (
    Optimize,
    Int,
    Bool,
    If,
    And,
    Or,
    Sum,
    sat,
)

from .dataset import Task, Worker


class Solver:
    def __init__(self):
        self.timeout = 300000

    def _build_predecessor_map(self, task: Task) -> dict[str, list[str]]:
        """Return a mapping from node_id -> list of predecessor node_ids."""
        preds: dict[str, list[str]] = {nid: [] for nid in task.nodes}
        for edge in task.edges:
            # Skip malformed edges where src or dst node was not found
            if edge.src is None or edge.dst is None:
                continue
            preds[edge.dst.id].append(edge.src.id)
        return preds

    def _compute_upper_bound(self, task: Task) -> int:
        """
        Compute a theoretical upper bound on the makespan by summing all processing times.
        This is a worst-case which assumes each node in a Task was executed sequentially.
        """
        return sum([node.proc_time for node in task.nodes.values()])

    def _compute_lower_bound(self, task: Task, preds: dict[str, list[str]]) -> int:
        """Compute a theoretical lower bound on the makespan"""
        nodes = task.nodes
        earliest_end: dict[str, int] = {}

        def _earliest(nid: str) -> int:
            if nid in earliest_end:
                return earliest_end[nid]
            if not preds[nid]:
                # Source node — can start at time 0
                earliest_end[nid] = nodes[nid].proc_time
            else:
                earliest_end[nid] = nodes[nid].proc_time + max(
                    _earliest(p) for p in preds[nid]
                )
            return earliest_end[nid]

        for nid in nodes:
            _earliest(nid)

        return max(earliest_end.values())

    def schedule_task(self, task: Task, workers: dict[str, Worker]) -> dict | None:
        """Solve a single Task and return the schedule, or None on failure."""

        opt = Optimize()
        opt.set("timeout", self.timeout)

        # Collect only the workers referenced by this task
        task_worker_ids = [wid for wid in task.workers if wid in workers]
        num_workers = len(task_worker_ids)

        # Create set of worker variables
        resource_types: set[str] = set()
        for wid in task_worker_ids:
            resource_types.update(workers[wid].provides.keys())
        resource_types = sorted(resource_types)  # deterministic order

        upper_bound = self._compute_upper_bound(task)
        preds = self._build_predecessor_map(task)
        lower_bound = self._compute_lower_bound(task, preds)

        node_ids = list(task.nodes.keys())
        nodes = task.nodes

        # Decision variables:

        # start[n] : integer start time for node n
        start = {nid: Int(f"start_{nid}") for nid in node_ids}

        # end[n] = start[n] + proc_time[n]
        end = {nid: start[nid] + nodes[nid].proc_time for nid in node_ids}

        # assign[n][w] : indicator if node n assigned to worker w
        assign: dict[str, dict[str, Bool]] = {}
        for nid in node_ids:
            assign[nid] = {}
            for wid in task_worker_ids:
                assign[nid][wid] = Bool(f"assign_{nid}_{wid}")

        # Constraint: 0 < start_time < upper bound
        for nid in node_ids:
            opt.add(start[nid] >= 0)
            opt.add(end[nid] <= upper_bound)

        # Constraint 2: Each node assigned to exactly one compatible worker
        for nid in node_ids:
            node = nodes[nid]
            compatible = [
                wid for wid in task_worker_ids if wid in node.compatible_workers
            ]

            # Must be assigned to exactly one worker (at-least-one + at-most-one)
            # At-least-one: disjunction of compatible assignments
            opt.add(Or([assign[nid][wid] for wid in compatible]))

            # Force incompatible assignments to False
            for wid in task_worker_ids:
                if wid not in compatible:
                    opt.add(assign[nid][wid] == False)

            # At-most-one (pairwise exclusion)
            for i in range(len(compatible)):
                for j in range(i + 1, len(compatible)):
                    opt.add(
                        Or(
                            assign[nid][compatible[i]] == False,
                            assign[nid][compatible[j]] == False,
                        )
                    )

        # Constraint 3: DAG precedence
        for nid in node_ids:
            for pred_id in preds[nid]:
                opt.add(start[nid] >= end[pred_id])

        # Constraint 4:
        # Ensure each node's Requires (utilization) at a given timestep
        # does not exceed the worker's Provides (capacity)
        #
        # A node M is "active" at time t on worker W iff:
        #     assign[M][W] AND start[M] <= t AND t < end[M]
        #
        for wid in task_worker_ids:
            worker = workers[wid]
            for res in resource_types:
                capacity = worker.provides.get(res, 0)

                # For each node's start time
                for n in node_ids:
                    t = start[n]

                    # Sum of demands of all nodes active on this worker at time t
                    demand_terms = []
                    for m in node_ids:
                        m_demand = nodes[m].requires.get(res, 0)
                        if m_demand == 0:
                            continue  # no contribution, skip
                        # m is active on wid at time t if assign[m][wid] AND start[m] <= t AND t < end[m]
                        demand_terms.append(
                            If(
                                And(
                                    assign[m][wid],  # if m is assigned to this worker
                                    start[m]
                                    <= t,  # and, if m would be executing during this timestep
                                    t < end[m],  # and, if m has not completed yet
                                ),
                                m_demand,  # then, log this node as having a demand on worker "w"
                                0,  # else, 0
                            )
                        )

                    if demand_terms:
                        opt.add(
                            Sum(demand_terms) <= capacity
                        )  # ensure that the total demand does not exceed capacity

        # Define the optimizer objective
        makespan = Int("makespan")
        for nid in node_ids:
            opt.add(makespan >= end[nid])
        opt.minimize(makespan)

        print(
            f"[solver] Solving task '{task.task_id}' "
            f"({len(node_ids)} nodes, {len(task.edges)} edges, "
            f"{num_workers} workers, LB={lower_bound}, UB={upper_bound}) ..."
        )

        # execute solver
        result = opt.check()

        if result != sat:
            print(
                f"[solver] Task '{task.task_id}': no solution found (result={result})."
            )
            return None

        model = opt.model()
        makespan_val = model.eval(makespan).as_long()

        # write out a valid schedule
        schedule: list[dict] = []
        for nid in node_ids:
            s = model.eval(start[nid]).as_long()
            e = model.eval(end[nid]).as_long()
            assigned_worker = None
            for wid in task_worker_ids:
                if model.eval(assign[nid][wid]):
                    assigned_worker = wid
                    break

            schedule.append(
                {
                    "node_id": nid,
                    "node_name": nodes[nid].name,
                    "worker_id": assigned_worker,
                    "start": s,
                    "end": e,
                    "processing_time": nodes[nid].proc_time,
                }
            )

        # Sort schedule by start time
        schedule.sort(key=lambda x: (x["start"], x["end"]))

        print(f"[solver] Task '{task.task_id}': optimal makespan = {makespan_val}")
        self._print_schedule(task.task_id, schedule, makespan_val, lower_bound)

        return {
            "makespan": makespan_val,
            "lower_bound": lower_bound,
            "schedule": schedule,
        }

    def _print_schedule(
        self, task_id: str, schedule: list[dict], makespan: int, lower_bound: int
    ) -> None:
        """Print a formatted schedule table."""
        hdr = (
            f"{'Node':<30s} {'Worker':<16s} {'Start':>6s} {'End':>6s} {'Duration':>8s}"
        )
        sep = "-" * len(hdr)
        print(
            f"\n  Schedule for task: {task_id}  (makespan = {makespan}, lower bound = {lower_bound})"
        )
        print(f"  {sep}")
        print(f"  {hdr}")
        print(f"  {sep}")
        for entry in schedule:
            print(
                f"  {entry['node_name']:<30s} {entry['worker_id']:<16s} "
                f"{entry['start']:>6d} {entry['end']:>6d} "
                f"{entry['processing_time']:>8d}"
            )
        print(f"  {sep}\n")
