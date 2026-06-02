from .solver import Solver
from .dataset import Worker, Task
import json


def load_workers(fpath: str) -> list[Worker]:
    with open(fpath, "r") as file:
        worker_jsons = json.load(file)

    return {
        worker_json["worker_id"]: Worker(**worker_json) for worker_json in worker_jsons
    }


def load_workflows(fpath: str) -> list[Task]:
    with open(fpath, "r") as file:
        tasks_json = json.load(file)

    return [Task(**task) for task in tasks_json]


def main():
    workers = load_workers("data/workers.json")
    tasks = load_workflows("data/workflows.json")
    solver = Solver()

    print(f"Loaded {len(workers)} workers and {len(tasks)} workflow tasks.\n")

    results = []
    for task in tasks:
        result = solver.schedule_task(task, workers)
        task.render_dag(f"img/{task.task_id}_dag.png")
        results.append((task.task_id, result))

    # Summary
    print("\n" + "=" * 72)
    print("  SCHEDULING SUMMARY")
    print("=" * 72)
    print(f"  {'Task':<40s} {'Makespan':>8s} {'LB':>8s} {'Gap':>8s}")
    print(f"  {'-' * 66}")
    for task_id, result in results:
        if result is not None:
            ms = result["makespan"]
            lb = result["lower_bound"]
            gap = ms - lb
            print(f"  {task_id:<40s} {ms:>8d} {lb:>8d} {gap:>+8d}")
        else:
            print(f"  {task_id:<40s} {'UNSOLVABLE':>8s}")
    print("=" * 72)


if __name__ == "__main__":
    main()
