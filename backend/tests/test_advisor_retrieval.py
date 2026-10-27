from app.modules.advisor.service import (
    NO_MATCH_ANSWER,
    build_search_plan,
    is_sensitive_query,
    make_answer,
)


def test_synonym_rules_expand_crop_and_problem_terms():
    plan = build_search_plan("मक्का के पत्तों पर जंग क्यों है")
    assert "maize" in plan.concepts
    assert "rust" in plan.concepts
    assert "maize" in plan.expanded_terms
    assert "rust" in plan.expanded_terms


def test_local_language_crop_names_are_supported():
    assert "tomato" in build_search_plan("टमाटर के पत्ते").concepts
    assert "potato" in build_search_plan("உருளைக்கிழங்கு இலை").concepts
    assert "grape" in build_search_plan("ద్రాక్ష ఆకులు").concepts


def test_user_text_cannot_inject_tsquery_operators():
    plan = build_search_plan("potato'; DROP TABLE knowledge_chunks; --")
    assert all(token.isalnum() for token in plan.expanded_terms)
    assert plan.tsquery == " | ".join(plan.expanded_terms)


def test_sensitive_dosage_requests_abstain():
    assert is_sensitive_query("What pesticide dose should I spray on maize?")
    assert is_sensitive_query("उर्वरक की मात्रा कितनी डालें")
    assert not is_sensitive_query("What are potato late blight symptoms?")


def test_no_match_has_an_explicit_local_library_fallback():
    assert "local agriculture library" in NO_MATCH_ANSWER
    assert make_answer([]) == NO_MATCH_ANSWER
