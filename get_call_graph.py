import argparse
import os

import tests4py.api as t4p
from tests4py.projects import TestStatus

from get_analysis import get_event_files


def build_call_graph(project):
    failing, passing, _ = get_event_files(project.events_base, project.mapping)


def main(project_name, bug_id):
    cg_dir = "call_graphs"
    os.makedirs(cg_dir, exist_ok=True)

    for project in t4p.get_projects(project_name, bug_id):
        identifier = project.get_identifier()
        print(identifier)
        if (
            project.test_status_buggy != TestStatus.FAILING
            or project.test_status_fixed != TestStatus.PASSING
        ):
            continue
        project.buggy = True


if __name__ == "__main__":
    args = argparse.ArgumentParser()
    args.add_argument("-p", required=True, dest="project_name", help="project name")
    args.add_argument("-i", default=None, dest="bug_id", help="bug_id")

    arguments = args.parse_args()
    name = arguments.project_name
    id_ = arguments.bug_id
    if id_ is not None:
        id_ = int(id_)

    main(name, id_)
