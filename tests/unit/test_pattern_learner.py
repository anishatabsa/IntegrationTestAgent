"""Unit tests for PatternLearner."""
import pytest

from aita.core.feedback.pattern_learner import PatternLearner
from aita.domain.enums import FeedbackSource, FeedbackType
from aita.domain.models import FeedbackItem


@pytest.fixture
def learner():
    return PatternLearner()


@pytest.mark.asyncio
async def test_empty_feedback_returns_no_patterns(learner):
    patterns = await learner.learn("svc", [])
    assert patterns == []


@pytest.mark.asyncio
async def test_learns_most_common_type(learner):
    feedback = [
        FeedbackItem(source=FeedbackSource.AUTO, feedback_type=FeedbackType.WRONG_STATUS_CODE,
                     description="expected 401 got 200"),
        FeedbackItem(source=FeedbackSource.AUTO, feedback_type=FeedbackType.WRONG_STATUS_CODE,
                     description="expected 403 got 200"),
        FeedbackItem(source=FeedbackSource.AUTO, feedback_type=FeedbackType.ASSERTION_FAILURE,
                     description="assert failed"),
    ]
    patterns = await learner.learn("svc", feedback)
    assert len(patterns) >= 1
    types = [p.pattern_type for p in patterns]
    assert str(FeedbackType.WRONG_STATUS_CODE) in types


@pytest.mark.asyncio
async def test_pattern_has_prompt_snippet(learner):
    feedback = [
        FeedbackItem(source=FeedbackSource.AUTO, feedback_type=FeedbackType.WRONG_STATUS_CODE,
                     description="expected 401 got 200"),
    ]
    patterns = await learner.learn("svc", feedback)
    assert patterns[0].prompt_snippet is not None
    assert len(patterns[0].prompt_snippet) > 0
