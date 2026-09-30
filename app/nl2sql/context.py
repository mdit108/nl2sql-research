"""The Context Ladder: one pipeline, where only the context given to the model changes.

    E0  question only
    E1  + schema (tables, columns, types)                       structured, from the catalog
    E2  + primary/foreign keys, relationships, cardinality      structured
    E3  + table/column descriptions                             structured
    E4  + business entity definitions                           retrieved (pgvector)
    E5  + metric definitions                                    retrieved (pgvector)
    E6  + domain rules and pitfalls                             retrieved (pgvector)
    E7  + worked examples                                       (not built yet)
    E8  E7 + validation and one correction                      (not built yet)
"""

from dataclasses import dataclass

from app.nl2sql.schema import load_descriptions, load_relationships, load_schema, render_schema
from app.retrieval.knowledge import KnowledgeRetriever, RetrievalResult, gold_items


@dataclass(frozen=True)
class Level:
    name: str
    schema: bool = False
    relational: bool = False
    descriptive: bool = False
    knowledge_types: tuple[str, ...] = ()


LEVELS = {
    "E0": Level("E0"),
    "E1": Level("E1", schema=True),
    "E2": Level("E2", schema=True, relational=True),
    "E3": Level("E3", schema=True, relational=True, descriptive=True),
    "E4": Level("E4", True, True, True, ("business_entity",)),
    "E5": Level("E5", True, True, True, ("business_entity", "metric")),
    "E6": Level("E6", True, True, True, ("business_entity", "metric", "domain_rule")),
}
NOT_YET_BUILT = {"E7", "E8"}

SECTION_TITLES = {
    "business_entity": "BUSINESS DEFINITIONS",
    "metric": "METRIC DEFINITIONS",
    "domain_rule": "DOMAIN RULES AND KNOWN PITFALLS",
}


@dataclass
class Context:
    level: str
    text: str
    retrieval: RetrievalResult | None


def get_level(name: str) -> Level:
    if name in NOT_YET_BUILT:
        raise NotImplementedError(f"{name} is planned but not built yet")
    if name not in LEVELS:
        raise ValueError(f"Unknown level {name!r}; expected one of {sorted(LEVELS)}")
    return LEVELS[name]


def render_knowledge(retrieval: RetrievalResult) -> str:
    parts = []
    for ktype in retrieval.knowledge_types:
        items = [i for i in retrieval.items if i.knowledge_type == ktype]
        if items:
            parts.append(f"{SECTION_TITLES[ktype]}:\n" + "\n".join(f"- {i.name}: {i.content}" for i in items))
    return "\n\n".join(parts)


def build_context(question: str, level_name: str, mode: str = "retrieved", top_k: int = 3,
                  gold_ids: list[str] | None = None, retriever: KnowledgeRetriever | None = None) -> Context:
    """mode="retrieved": pgvector top-k per type. mode="gold": the benchmark's gold items."""
    level = get_level(level_name)
    sections = []
    if level.schema:
        sections.append("DATABASE SCHEMA:\n" + render_schema(
            load_schema(), level.relational, level.descriptive, load_descriptions(), load_relationships()))

    retrieval = None
    if level.knowledge_types:
        types = list(level.knowledge_types)
        if mode == "gold":
            retrieval = gold_items(gold_ids or [], types)
        else:
            retrieval = (retriever or KnowledgeRetriever()).search(question, types, top_k)
        knowledge = render_knowledge(retrieval)
        if knowledge:
            sections.append(knowledge)

    return Context(level=level.name, text="\n\n".join(sections), retrieval=retrieval)
