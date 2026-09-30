from app.nl2sql.context import render_knowledge
from app.nl2sql.prompt import load_prompt
from app.retrieval.knowledge import KnowledgeItem, RetrievalResult


def test_template_has_slots_and_renders():
    tpl = load_prompt("generation/v1")
    assert "{context}" in tpl.text and "{question}" in tpl.text
    prompt = tpl.render("How many orders?", "DATABASE SCHEMA:\nTABLE orders")
    assert prompt.rstrip().endswith("Question: How many orders?")
    assert "TABLE orders" in prompt
    assert "{context}" not in prompt and "{question}" not in prompt


def test_e0_prompt_has_no_context_but_same_instructions():
    tpl = load_prompt("generation/v1")
    e0 = tpl.render("How many orders?", "")
    e1 = tpl.render("How many orders?", "DATABASE SCHEMA:\nTABLE orders")
    assert "DATABASE SCHEMA" not in e0
    assert e0.split("\n\nQuestion:")[0] in e1  # instructions identical across levels


def test_prompt_hash_is_stable():
    assert load_prompt().hash == load_prompt().hash


def test_knowledge_sections_follow_level_types():
    items = [
        KnowledgeItem("ent.customer", "business_entity", "Customer", "A customer is a person."),
        KnowledgeItem("met.revenue", "metric", "Revenue", "SUM(price)."),
    ]
    r = RetrievalResult("q", 3, ["business_entity", "metric"], items, 0.0)
    text = render_knowledge(r)
    assert text.index("BUSINESS DEFINITIONS") < text.index("METRIC DEFINITIONS")
    assert "- Customer: A customer is a person." in text
