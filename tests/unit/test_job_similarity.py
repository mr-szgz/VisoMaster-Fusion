import copy

import pytest

from app.helpers.job_similarity import (
    add_job_to_cluster,
    configuration_differences,
    saved_render_configuration,
)


@pytest.fixture
def job():
    return {
        "control": {
            "ProvidersPrioritySelection": "TensorRT-Engine",
            "KeepModelsAliveToggle": True,
        },
        "target_faces_data": {
            "face": {
                "parameters": {
                    "SwapModelSelection": "Inswapper128",
                    "SecondarySwapModelSelection": "AlphaFace",
                    "FaceRestorerTypeSelection": "OSDFace",
                    "HairMattingEnableToggle": False,
                }
            }
        },
        "markers": {},
        "job_marker_pairs": [],
        "dropped_frames": [],
        "swap_faces_enabled": True,
        "edit_faces_enabled": True,
    }


@pytest.mark.parametrize(
    "section,key,value",
    [
        ("control", "ProvidersPrioritySelection", "CUDA"),
        ("parameters", "SecondarySwapModelSelection", "Inswapper128"),
        ("parameters", "FaceRestorerTypeSelection", "GFPGAN-v1.4"),
        ("parameters", "HairMattingEnableToggle", True),
        ("parameters", "HairMattingEnableToggle", 0),
    ],
)
def test_all_saved_values_and_types_must_match(job, section, key, value):
    candidate = copy.deepcopy(job)
    target = (
        candidate["control"]
        if section == "control"
        else candidate["target_faces_data"]["face"]["parameters"]
    )
    target[key] = value
    differences = configuration_differences(
        saved_render_configuration(job), saved_render_configuration(candidate)
    )
    assert len(differences) == 1
    assert f"{section}.{key}" in differences[0]


def test_face_ids_and_dictionary_order_do_not_matter(job):
    candidate = copy.deepcopy(job)
    candidate["target_faces_data"]["another-face"] = candidate["target_faces_data"].pop(
        "face"
    )
    candidate["control"] = dict(reversed(list(candidate["control"].items())))
    assert not configuration_differences(
        saved_render_configuration(job), saved_render_configuration(candidate)
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("markers", {"1": {"parameters": {}}}),
        ("job_marker_pairs", [[0, 10]]),
        ("dropped_frames", [10]),
        ("target_faces_data", {}),
    ],
)
def test_timing_and_face_settings_are_compared_without_batch_restrictions(
    job, field, value
):
    candidate = copy.deepcopy(job)
    candidate[field] = value
    saved = saved_render_configuration(candidate)
    assert not configuration_differences(
        saved, saved_render_configuration(copy.deepcopy(candidate))
    )
    assert configuration_differences(saved_render_configuration(job), saved)


def test_equal_sparse_jobs_match(job):
    del job["control"]["KeepModelsAliveToggle"]
    del job["target_faces_data"]["face"]["parameters"]["HairMattingEnableToggle"]
    saved = saved_render_configuration(job)
    candidate = saved_render_configuration(copy.deepcopy(job))
    assert not configuration_differences(saved, candidate)


def test_setting_saved_in_only_one_job_is_a_difference(job):
    candidate = copy.deepcopy(job)
    del candidate["target_faces_data"]["face"]["parameters"]["HairMattingEnableToggle"]
    differences = configuration_differences(
        saved_render_configuration(job), saved_render_configuration(candidate)
    )
    assert differences == [
        "parameters.HairMattingEnableToggle: reference = False; absent in job"
    ]


def test_unknown_disabled_settings_and_button_states_remain_significant(job):
    candidate = copy.deepcopy(job)
    candidate["target_faces_data"]["face"]["parameters"]["FutureModelSetting"] = "test"
    candidate["edit_faces_enabled"] = False
    differences = configuration_differences(
        saved_render_configuration(job), saved_render_configuration(candidate)
    )
    assert any("FutureModelSetting" in reason for reason in differences)
    assert any("edit_faces_enabled" in reason for reason in differences)


def test_multiple_faces_and_marker_parameters_ignore_face_ids_and_order(job):
    job["target_faces_data"]["second"] = copy.deepcopy(job["target_faces_data"]["face"])
    job["target_faces_data"]["second"]["parameters"]["HairMattingEnableToggle"] = True
    job["markers"] = {
        "10": {
            "control": {},
            "parameters": {
                "face": {"HairMattingEnableToggle": True},
                "second": {"HairMattingEnableToggle": False},
            },
        }
    }
    candidate = copy.deepcopy(job)
    candidate["target_faces_data"] = {
        "new-second": candidate["target_faces_data"]["second"],
        "new-first": candidate["target_faces_data"]["face"],
    }
    candidate["markers"]["10"]["parameters"] = {
        "new-second": {"HairMattingEnableToggle": False},
        "new-first": {"HairMattingEnableToggle": True},
    }
    assert not configuration_differences(
        saved_render_configuration(job), saved_render_configuration(candidate)
    )
    candidate["markers"]["10"]["parameters"]["new-first"]["HairMattingEnableToggle"] = (
        False
    )
    assert configuration_differences(
        saved_render_configuration(job), saved_render_configuration(candidate)
    )


def test_jobs_join_existing_clusters_in_encounter_order(job):
    clusters = []
    for name, strength in [("A", 90), ("B", 80), ("C", 70), ("D", 80), ("E", 90)]:
        data = copy.deepcopy(job)
        data["target_faces_data"]["face"]["parameters"]["StrengthAmountSlider"] = (
            strength
        )
        add_job_to_cluster(clusters, name, saved_render_configuration(data))
    assert [cluster["id"] for cluster in clusters] == [1, 2, 3]
    assert [cluster["jobs"] for cluster in clusters] == [["A", "E"], ["B", "D"], ["C"]]
    assert [cluster["representative_job"] for cluster in clusters] == ["A", "B", "C"]


def test_cluster_calculation_has_no_display_limit(job):
    clusters = []
    for index in range(12):
        data = copy.deepcopy(job)
        data["target_faces_data"]["face"]["parameters"]["StrengthAmountSlider"] = index
        add_job_to_cluster(clusters, str(index), saved_render_configuration(data))
    assert len(clusters) == 12
    assert sum(len(cluster["jobs"]) for cluster in clusters) == 12
