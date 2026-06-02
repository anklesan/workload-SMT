# Workflow-Z3: A Distributed Compute Workflow Solver using SMT Solver
A final project for CS-517 Theory of Computation @ Oregon State University, Spring 2027
Contributors:
- Laura Kuo
- Ninad Anklesaria
- Aidan Beery

# Installation
To run this code, it is recommended to use the `uv` python build tool. You can install uv [here](https://docs.astral.sh/uv/getting-started/installation/)
Once you have `uv` installed, you can install the dependencies by running `uv sync`

# Usage
To run this script, use `uv run run-solver`. This will read the list of workflows in `data/workflows.json` and output an efficient workload schedule, based on the compute resource constraints defined in `data/workers.json`.


