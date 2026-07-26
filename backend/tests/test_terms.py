from aisle.cluster.terms import c_tf_idf, tokenize


def test_tokenize_drops_stopwords():
    tokens = tokenize("The pomegranates were split and dry, third time this month.")
    assert "the" not in tokens
    assert "pomegranates" in tokens


def test_c_tf_idf_favours_terms_distinctive_to_one_cluster():
    cluster_texts = {
        0: ["freshness freshness produce quality"] * 3,
        1: ["delivery delivery time late again"] * 3,
    }
    result = c_tf_idf(cluster_texts, top_k=3)
    assert "freshness" in result[0]
    assert "delivery" in result[1]
    assert "freshness" not in result[1]


def test_c_tf_idf_returns_requested_top_k_at_most():
    cluster_texts = {0: ["one two three four five six seven eight nine ten eleven"]}
    result = c_tf_idf(cluster_texts, top_k=3)
    assert len(result[0]) <= 3
