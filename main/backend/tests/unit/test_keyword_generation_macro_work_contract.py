from app.services.llm.macro_work import KEYWORD_GENERATION_WORK


def test_keyword_generation_work_binding_captures_existing_boundary():
    work = KEYWORD_GENERATION_WORK

    assert work.entrypoint == "app.services.keyword_generation.generate_social_keywords"
    assert work.input_fields == (
        "topic",
        "language",
        "platform",
        "base_keywords",
        "return_combined",
    )
    assert "combined mode returns" in work.result_contract
    assert "Chinese and English" in work.result_contract
    assert "no-key" in work.failure_contract
    assert "clean keywords" in work.effects
    assert "store non-empty search keywords for platform" in work.effects
    assert len(work.consumers) == 3
    assert "no recursive Agent" in work.execution_boundary


def test_keyword_generation_skill_content_is_the_declared_source():
    from pathlib import Path

    skill = Path(__file__).parents[2] / "skills/keyword-generation/SKILL.md"
    content = skill.read_text(encoding="utf-8")

    assert KEYWORD_GENERATION_WORK.skill_path.endswith("skills/keyword-generation/SKILL.md")
    assert "does not itself establish native skill mounting or execution" in content
    assert "get_chat_model()" in content
    assert "Combined mode" in content
    assert "Legacy mode" in content
