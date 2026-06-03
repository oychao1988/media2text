from media2text.core.summarize.sections import parse_sections_from_markdown


def test_parse_sections_from_markdown() -> None:
    md = """## 核心观点
- 观点一
- 观点二

## 风险提示
原文提及波动"""
    sections = parse_sections_from_markdown(md)
    assert len(sections) == 2
    assert sections[0]["title"] == "核心观点"
    assert "观点一" in sections[0]["content"]
    assert sections[1]["title"] == "风险提示"


def test_parse_sections_empty() -> None:
    assert parse_sections_from_markdown("") == []
    assert parse_sections_from_markdown("no headings here") == []
