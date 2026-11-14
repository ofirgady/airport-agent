from airport_investment_agent.utils.caveats import merge_unique


def test_merge_unique_preserves_first_seen_order():
    assert merge_unique(["a", "b"], ["c"]) == ["a", "b", "c"]


def test_merge_unique_drops_duplicates_keeping_first_occurrence():
    assert merge_unique(["a", "b"], ["b", "c"]) == ["a", "b", "c"]


def test_merge_unique_handles_more_than_two_lists():
    assert merge_unique(["a"], ["b", "a"], ["c", "b"]) == ["a", "b", "c"]


def test_merge_unique_handles_empty_lists():
    assert merge_unique([], []) == []
    assert merge_unique() == []
    assert merge_unique(["a"], []) == ["a"]


def test_merge_unique_supports_generator_argument():
    lists = ([f"x{i}"] for i in range(3))
    assert merge_unique(*lists) == ["x0", "x1", "x2"]
