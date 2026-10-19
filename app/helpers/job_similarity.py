"""Compare saved rendering settings without loading a workspace or any models."""

import json


def saved_render_configuration(data: dict) -> dict:
    # Match face settings and their marker changes independently of saved face IDs.
    faces = sorted(
        data["target_faces_data"].items(),
        key=lambda face: json.dumps(
            {
                "parameters": face[1]["parameters"],
                "markers": {
                    frame: marker["parameters"][face[0]]
                    for frame, marker in data["markers"].items()
                    if face[0] in marker["parameters"]
                },
            },
            sort_keys=True,
        ),
    )
    parameters = [face["parameters"] for _, face in faces]
    face_indices = {face_id: str(index) for index, (face_id, _) in enumerate(faces)}
    markers = {
        frame: {
            **marker,
            "parameters": {
                face_indices[face_id]: values
                for face_id, values in marker["parameters"].items()
            },
        }
        for frame, marker in data["markers"].items()
    }
    return {
        "control": data["control"],
        "parameters": parameters,
        "swap_faces_enabled": data["swap_faces_enabled"],
        "edit_faces_enabled": data["edit_faces_enabled"],
        "markers": markers,
        "job_marker_pairs": data["job_marker_pairs"],
        "dropped_frames": data["dropped_frames"],
    }


def configuration_differences(reference: dict, candidate: dict) -> list[str]:
    """Keep every saved setting, including disabled settings and unknown keys."""
    differences = []
    sections = [("control", reference["control"], candidate["control"])]
    if len(reference["parameters"]) != len(candidate["parameters"]):
        differences.append(
            f"Face parameter sets: reference = {len(reference['parameters'])}; "
            f"job = {len(candidate['parameters'])}"
        )
    for index, (expected, actual) in enumerate(
        zip(reference["parameters"], candidate["parameters"]), 1
    ):
        section = (
            "parameters"
            if len(reference["parameters"]) == len(candidate["parameters"]) == 1
            else f"face {index} parameters"
        )
        sections.append((section, expected, actual))
    for section, expected, actual in sections:
        for key in sorted(expected.keys() | actual.keys()):
            path = f"{section}.{key}"
            if key not in expected:
                differences.append(
                    f"{path}: absent in reference; job = {actual[key]!r}"
                )
            elif key not in actual:
                differences.append(
                    f"{path}: reference = {expected[key]!r}; absent in job"
                )
            elif json.dumps(expected[key], sort_keys=True) != json.dumps(
                actual[key], sort_keys=True
            ):
                differences.append(
                    f"{path}: reference = {expected[key]!r}; job = {actual[key]!r}"
                )
    for key in (
        "swap_faces_enabled",
        "edit_faces_enabled",
        "markers",
        "job_marker_pairs",
        "dropped_frames",
    ):
        if json.dumps(reference[key], sort_keys=True) != json.dumps(
            candidate[key], sort_keys=True
        ):
            differences.append(
                f"{key}: reference = {reference[key]}; job = {candidate[key]}"
            )
    return differences
