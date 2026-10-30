"""Evaluator contract only; these tests do not claim vision/model execution."""
import importlib.util
from pathlib import Path
import sys
import pytest
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'tools'))
spec=importlib.util.spec_from_file_location('qa_review_cases',ROOT/'tools/verification/review_cases.py')
review=importlib.util.module_from_spec(spec);spec.loader.exec_module(review)

@pytest.mark.parametrize('changed',['model_id','model_path','projector','device','n_ctx','chat_template_sha256','messages_sha256','options_sha256'])
def test_same_image_alone_cannot_establish_matched_vision_comparison(changed):
    left={key:'same' for key in ['model_id','model_path','projector','device','n_ctx','chat_template_sha256','messages_sha256','options_sha256','image_sha256']}
    right={**left,changed:'different'}
    equality=review.matched_native_inputs(left,right)
    assert equality['image_sha256'] and not all(equality.values())
