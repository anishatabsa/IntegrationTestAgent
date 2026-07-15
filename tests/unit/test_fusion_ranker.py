"""Unit tests for RRF fusion ranker."""
from aita.core.knowledge.fusion_ranker import rrf_fuse


def test_single_list_preserves_order():
    items = ["a", "b", "c"]
    result = rrf_fuse([items])
    assert result == items


def test_two_lists_promote_agreement():
    list1 = ["a", "b", "c"]
    list2 = ["b", "a", "d"]
    result = rrf_fuse([list1, list2])
    # "a" and "b" appear in both — should rank above "c" and "d"
    assert result.index("a") < result.index("c")
    assert result.index("b") < result.index("d")


def test_empty_lists():
    assert rrf_fuse([]) == []
    assert rrf_fuse([[]]) == []


def test_deduplication():
    list1 = ["a", "a", "b"]
    result = rrf_fuse([list1])
    assert len(result) == len(set(result))
