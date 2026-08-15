import json

from validation.reevaluate import reevaluate_report


def test_reevaluate_preserves_original_evidence(tmp_path) -> None:
    source = tmp_path / "source.json"
    target = tmp_path / "reevaluated.json"
    source.write_text(
        json.dumps(
            {
                "runs": [
                    {
                        "turns": [
                            {
                                "teacher_input": "y=4x-2 和 y=4x+7 哪一条更陡？",
                                "student_response": "嗯……我觉得它们一样陡吧，因为 k 都是 4，陡的程度应该由 k 决定。区别就是 b 不一样，一个在下面一点，一个在上面一点。",
                                "student_response_evidence": {"transfer_success": False},
                            }
                        ]
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    output = reevaluate_report(source, target)
    payload = json.loads(output.read_text(encoding="utf-8"))
    turn = payload["runs"][0]["turns"][0]

    assert turn["original_student_response_evidence"] == {"transfer_success": False}
    assert turn["reevaluated_student_response_evidence"]["transfer_success"] is True
    assert source.read_text(encoding="utf-8") != output.read_text(encoding="utf-8")
