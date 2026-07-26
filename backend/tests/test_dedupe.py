from aisle.ingest.dedupe import content_hash, hamming_distance, is_near_duplicate, simhash


def test_content_hash_is_stable_and_case_insensitive():
    a = content_hash("The pomegranates were split and dry.")
    b = content_hash("the   POMEGRANATES were split and dry.")
    assert a == b


def test_content_hash_differs_for_different_text():
    a = content_hash("great app love it")
    b = content_hash("terrible app hate it")
    assert a != b


def test_simhash_near_duplicates_detected():
    a = simhash("the pomegranates I ordered on Tuesday were split and dry")
    b = simhash("the pomegranates I ordered on Tuesday were split and dry again")
    assert is_near_duplicate(a, b, similarity_threshold=0.75)


def test_simhash_distinct_text_not_flagged_near_dup():
    a = simhash("the pomegranates I ordered on Tuesday were split and dry")
    b = simhash("delivery partner could not find my address at all today")
    assert not is_near_duplicate(a, b, similarity_threshold=0.9)


def test_hamming_distance_zero_for_identical():
    h = simhash("some review text")
    assert hamming_distance(h, h) == 0
