from z3 import *
import json


class Worker:
    def __init__(self, worker_id: str, device_name: str, provides: dict, location: str):
        self.worker_id = worker_id
        self.device_name = device_name
        self.provides = provides
        self.location = location


def load_workers(fpath: str) -> list[Worker]:
    with open(fpath, "r") as file:
        worker_jsons = json.load(file)

    return [Worker(**worker_json) for worker_json in worker_jsons]


def main():
    workers = load_workers("data/workers.json")
    for w in workers:
        print(w)


if __name__ == "__main__":
    main()
