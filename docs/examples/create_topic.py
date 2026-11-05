# This file was generated with the assistance of an AI coding tool.
"""Create a BCF topic with a viewpoint and a comment.

    uv run python docs/examples/create_topic.py https://cde.example my-client-id PROJECT_ID snapshot.png

The viewpoint selects three elements by IFC guid, colours one of them red and
carries the PNG as snapshot. Replace the guids with elements of your model.
"""

import sys
from pathlib import Path

from opencde_client import OpenCdeClient
from opencde_client.bcf import image_payload

ELEMENTS = ["1Xezbq735AdBO_4DerG66G", "3eT96F_cnDsOufCEsotwtp", "3k3LbXmTfDWODxdSuyCGYE"]


def main(server: str, client_id: str, project_id: str, snapshot: Path) -> None:
    with OpenCdeClient(server, client_id=client_id) as cde:
        cde.login()
        extensions = cde.bcf.extensions(project_id)
        topic = cde.bcf.create_topic(
            project_id,
            {
                "title": "Wall type does not match the schedule",
                "topic_type": extensions["topic_type"][0],
                "topic_status": extensions["topic_status"][0],
                "priority": extensions["priority"][-1],
                "labels": extensions["topic_label"][:1],
                "description": "Compare the three marked walls with the wall schedule, revision C.",
            },
        )
        print(f"topic {topic['server_assigned_id']} {topic['guid']}")

        kind, data = image_payload(snapshot.read_bytes())
        viewpoint = cde.bcf.create_viewpoint(
            project_id,
            topic["guid"],
            {
                "perspective_camera": {
                    "camera_view_point": {"x": 12.0, "y": -8.0, "z": 4.0},
                    "camera_direction": {"x": -0.6, "y": 0.7, "z": -0.3},
                    "camera_up_vector": {"x": 0.0, "y": 0.0, "z": 1.0},
                    "field_of_view": 60.0,
                    "aspect_ratio": 1.78,
                },
                "snapshot": {"snapshot_type": kind, "snapshot_data": data},
                "components": {
                    "selection": [{"ifc_guid": guid} for guid in ELEMENTS],
                    "coloring": [{"color": "FF0000", "components": [{"ifc_guid": ELEMENTS[0]}]}],
                    "visibility": {"default_visibility": True},
                },
            },
        )
        cde.bcf.create_comment(
            project_id, topic["guid"], {"comment": "See the marked walls.", "viewpoint_guid": viewpoint["guid"]}
        )
        for event in cde.bcf.topic_events(project_id, topic["guid"]):
            print(event["date"], [action["type"] for action in event["actions"]])


if __name__ == "__main__":
    if len(sys.argv) != 5:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2], sys.argv[3], Path(sys.argv[4]))
