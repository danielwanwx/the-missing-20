from scripts.diagnostics.eval_public_barcode_corpus import classify


def test_extra_wrong_code_cannot_hide_behind_one_correct_decode():
    case = {"expected_code": "070097025088", "format": "upc_a"}
    correct = {"rawValue": case["expected_code"], "format": case["format"]}
    wrong = {"rawValue": "070097026788", "format": "upc_a"}
    assert classify({"codes": [correct]}, case) == "correct"
    assert classify({"codes": [correct, wrong]}, case) == "wrong"
    assert classify({"codes": [wrong]}, case) == "wrong"
    conflict = "Conflicting barcode readings; reduce glare and scan again."
    assert classify({"codes": [correct], "error": conflict}, case) == "wrong"
    assert classify({"codes": [], "error": conflict}, case) == "abstain"
    assert classify({"codes": [], "error": "Unexpected TypeError"}, case) == "error"
    assert classify({"codes": [{**correct, "cornerPoints": []}]}, case) == "correct"
    assert classify({"codes": []}, case) == "abstain"
