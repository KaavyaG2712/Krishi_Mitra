from __future__ import annotations

from dataclasses import dataclass
import re
import unicodedata
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session
from google import genai
from google.genai import types
from app.modules.advisor.translation import LANGUAGES, Language


NO_MATCH_ANSWER = (
    "I could not find a sufficiently relevant passage in KrishiMitra's local agriculture library. "
    "Try naming the crop and problem, or ask your local KVK/agricultural officer."
)
MAX_RESULTS = 3
MAX_CANDIDATES = 20

# Compact, auditable rules expand common farmer terms into the crop and topic
# vocabulary used in the curated documents. This is query normalization, not
# generated advice. Add reviewed terms as the corpus grows.
SYNONYMS: dict[str, tuple[str, ...]] = {
    "tomato": ("tomato", "tomatoes", "tamatar", "टमाटर", "தக்காளி", "టమాటా", "టమోటా"),
    "potato": ("potato", "potatoes", "aloo", "alu", "आलू", "உருளைக்கிழங்கு", "బంగాళాదుంప"),
    "maize": ("maize", "corn", "makka", "मक्का", "மக்காச்சோளம்", "మొక్కజొన్న"),
    "grape": ("grape", "grapes", "अंगूर", "திராட்சை", "ద్రాక్ష"),
    "blight": ("blight", "early blight", "late blight", "झुलसा", "తెగులు"),
    "black_rot": ("black rot", "grape black rot", "काला सड़न", "கருப்பு அழுகல்", "నల్ల కుళ్ళు"),
    "rust": ("rust", "common rust", "जंग", "துரு நோய்", "కుంకుమ తెగులు"),
    "leaf": ("leaf", "leaves", "foliage", "पत्ता", "पत्ते", "இலை", "ఆకు"),
    "spot": ("spot", "spots", "lesion", "lesions", "धब्बा", "धब्बे", "புள்ளி", "మచ్చ"),
    "irrigation": ("irrigation", "irrigate", "watering", "water", "सिंचाई", "पानी", "நீர்ப்பாசனம்", "నీటిపారుదల"),
    "soil": ("soil", "मिट्टी", "மண்", "నేల"),
    "fertilizer": ("fertilizer", "fertiliser", "manure", "खाद", "உரம்", "ఎరువు"),
    "pest": ("pest", "insect", "कीट", "பூச்சி", "పురుగు"),
    "disease": ("disease", "infection", "रोग", "நோய்", "వ్యాధి"),
    "management": ("management", "control", "treatment", "manage", "उपाय", "नियंत्रण", "கட்டுப்பாடு", "నివారణ"),
    "ipm": ("ipm", "integrated pest management", "कीट प्रबंधन", "ஒருங்கிணைந்த பூச்சி மேலாண்மை", "సమగ్ర సస్యరక్షణ"),
}

SENSITIVE_QUERY = re.compile(
    r"\b(?:dose|dosage|how much|quantity|rate per|ml per|grams? per|kg per|spray schedule|chemical recommendation)\b"
    r"|(?:कितना|मात्रा|डोज|खुराक|அளவு|எவ்வளவு|మోతాదు|ఎంత)"
    r"|\b(?:pesticide|fungicide|insecticide|herbicide|fertili[sz]er)\b.{0,40}\b(?:dose|dosage|quantity|rate|apply|spray)\b",
    re.IGNORECASE,
)

STOP_WORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "do", "does", "for", "from", "how", "i", "in",
    "is", "it", "my", "of", "on", "or", "should", "the", "to", "what", "when", "which", "with", "मेरी",
    "में", "का", "की", "के", "है", "और", "क्या", "कैसे", "என்ன", "எப்படி", "இல்", "மற்றும்", "ఏమి", "ఎలా",
    "లో", "మరియు",
}


@dataclass(frozen=True)
class SearchPlan:
    original_terms: tuple[str, ...]
    expanded_terms: tuple[str, ...]
    concepts: tuple[str, ...]
    tsquery: str


@dataclass(frozen=True)
class KnowledgeHit:
    chunk_id: UUID
    document_id: UUID
    title: str
    publisher: str
    source_url: str
    page_number: int | None
    section: str | None
    text: str
    score: float


def _tokens(text_value: str) -> list[str]:
    normalized = unicodedata.normalize("NFKC", text_value).casefold()
    # Python's ``\w`` excludes Unicode combining marks. That splits many
    # Indic-script words into fragments, so group letters, numbers and marks
    # by Unicode category instead.
    tokens: list[str] = []
    current: list[str] = []
    for character in normalized:
        category = unicodedata.category(character)
        if category[0] in {"L", "N", "M"}:
            current.append(character)
        elif current:
            tokens.append("".join(current))
            current.clear()
    if current:
        tokens.append("".join(current))
    return [token for token in tokens if token not in STOP_WORDS and (len(token) > 1 or not token.isascii())]


def build_search_plan(question: str) -> SearchPlan:
    normalized = unicodedata.normalize("NFKC", question).casefold()
    original = _tokens(normalized)
    concepts: list[str] = []
    expanded = list(original)
    for concept, aliases in SYNONYMS.items():
        for alias in aliases:
            alias_normalized = unicodedata.normalize("NFKC", alias).casefold()
            if re.search(rf"(?<!\w){re.escape(alias_normalized)}(?!\w)", normalized, flags=re.UNICODE):
                concepts.append(concept)
                expanded.extend(_tokens(concept.replace("_", " ")))
                expanded.extend(_tokens(alias))
    expanded_terms = tuple(dict.fromkeys(expanded))[:40]
    # Tokens have been reduced to Unicode letters/numbers, so this expression
    # cannot inject tsquery operators or SQL into the database query.
    tsquery = " | ".join(expanded_terms)
    return SearchPlan(
        original_terms=tuple(dict.fromkeys(original)),
        expanded_terms=expanded_terms,
        concepts=tuple(dict.fromkeys(concepts)),
        tsquery=tsquery,
    )


def retrieve_passages(db: Session, question: str, *, limit: int = MAX_RESULTS) -> list[KnowledgeHit]:
    plan = build_search_plan(question)
    if not plan.tsquery:
        return []

    statement = text(
        """
        WITH q AS (SELECT to_tsquery('simple', :tsquery) AS query)
        SELECT c.id AS chunk_id, c.document_id, d.title, d.publisher, d.source_url,
               c.page_number, c.metadata_json, c.chunk_text,
               tsvector_to_array(c.search_vector) AS lexemes,
               ts_rank_cd(c.search_vector, q.query, 32) AS rank
        FROM knowledge_chunks AS c
        JOIN knowledge_documents AS d ON d.id = c.document_id
        CROSS JOIN q
        WHERE c.search_vector @@ q.query
        ORDER BY rank DESC, c.page_number NULLS LAST
        LIMIT :candidate_limit
        """
    )
    rows = db.execute(statement, {"tsquery": plan.tsquery, "candidate_limit": MAX_CANDIDATES}).mappings().all()
    hits: list[KnowledgeHit] = []
    for row in rows:
        metadata = row["metadata_json"] or {}
        tags = {str(tag).casefold() for tag in metadata.get("tags", [])}
        lexemes = {str(lexeme).casefold() for lexeme in (row["lexemes"] or [])}
        matched_terms = set(plan.original_terms) & lexemes
        matched_concepts = set(plan.concepts) & tags
        expanded_matches = set(plan.expanded_terms) & lexemes

        # A lone generic word is not enough to produce agricultural guidance.
        # A recognized crop/topic plus matching source metadata is acceptable.
        has_specific_match = bool(matched_concepts) or len(matched_terms) >= 2
        if not has_specific_match or not expanded_matches:
            continue

        rank = max(0.0, min(1.0, float(row["rank"] or 0.0)))
        coverage = min(1.0, len(matched_terms) / max(1, len(plan.original_terms)))
        score = min(1.0, rank + 0.25 * coverage + (0.12 if matched_concepts else 0.0))
        if score < 0.12:
            continue
        hits.append(
            KnowledgeHit(
                chunk_id=row["chunk_id"],
                document_id=row["document_id"],
                title=row["title"],
                publisher=row["publisher"],
                source_url=row["source_url"],
                page_number=row["page_number"],
                section=metadata.get("section"),
                text=row["chunk_text"].strip(),
                score=score,
            )
        )

    # Prefer distinct source pages so citations represent more than one passage
    # from a single long PDF. Stable ordering makes results reproducible.
    hits.sort(key=lambda hit: (-hit.score, hit.document_id.hex, hit.page_number or 0))
    unique: list[KnowledgeHit] = []
    seen: set[tuple[UUID, int | None]] = set()
    for hit in hits:
        key = (hit.document_id, hit.page_number)
        if key in seen:
            continue
        seen.add(key)
        unique.append(hit)
        if len(unique) >= max(1, min(limit, MAX_RESULTS)):
            break
    return unique


def make_answer(hits: list[KnowledgeHit]) -> str:
    if not hits:
        return NO_MATCH_ANSWER
    return "\n\n".join(hit.text for hit in hits)


def is_sensitive_query(question: str) -> bool:
    return bool(SENSITIVE_QUERY.search(question))


class AdvisorGenerationError(RuntimeError):
    def __init__(self, message: str, *, status_code: int = 502) -> None:
        super().__init__(message)
        self.status_code = status_code


AGRONOMY_SYSTEM_INSTRUCTION = """
You are KrishiMitra, a knowledgeable and practical agricultural advisor. Answer
genuine questions about agriculture, crops, soil, irrigation, plant health,
farm planning, and the KrishiMitra project. Politely decline unrelated topics.
Always respond in English; do not translate the question or answer.

Use your own broad agronomy knowledge to answer the farmer's actual question.
The retrieved passages are optional supporting references, not a script and not
the only permitted knowledge. Do not copy a passage verbatim or repeat the same
generic answer for different questions. Explain practical options, trade-offs,
and what information would change the recommendation. Prefer ICAR, agricultural
universities, KVKs, and government sources, but do not limit answers to them.
Use Google Search when the question needs current information or the local
library and your knowledge do not provide a reliable answer. Cite sources only
for claims they support; clearly distinguish general guidance from sourced
facts. If no passage is relevant, still answer using your agronomy knowledge.

Never invent a diagnosis, local weather, legal rule, or source. Do not give
specific pesticide/fertilizer application rates, mixing instructions, or spray
schedules. For chemical choice/dosage, poisoning, or severe crop loss, direct
the user to the product label and a local KVK/agricultural officer. Use clear,
helpful Markdown and finish the answer completely.
""".strip()


def generate_agronomy_answer(question: str, hits: list[KnowledgeHit], *, api_key: str, model: str, answer_language: Language = "en") -> tuple[str, list[dict[str, str]]]:
    excerpts = "\n\n".join(
        f"[{index}] {hit.title} ({hit.publisher}, page {hit.page_number or 'not stated'})\n{hit.text}"
        for index, hit in enumerate(hits, start=1)
    ) or "No matching local passage was found. Answer from your general agronomy knowledge and be transparent about uncertainty."
    prompt = f"Farmer's question:\n{question}\n\nOptional retrieved references:\n{excerpts}\n\nAnswer the question directly and use your own agronomy expertise."
    try:
        with genai.Client(api_key=api_key, http_options=types.HttpOptions(timeout=30000, retry_options=types.HttpRetryOptions(attempts=1))) as client:
            try:
                response = client.models.generate_content(
                    model=model,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                    system_instruction=AGRONOMY_SYSTEM_INSTRUCTION.replace("Always respond in English; do not translate the question or answer.", f"Always respond in {LANGUAGES[answer_language]}, using its native script. Keep crop names, units, chemical names and numeric values accurate."),
                        temperature=0.45,
                        max_output_tokens=1800,
                        tools=[types.Tool(google_search=types.GoogleSearch())],
                    ),
                )
            except Exception as search_error:
                # Search grounding can hit a separate quota from text generation.
                # Retry as a normal Gemini answer so exhausted search quota does
                # not make the entire farming advisor unavailable.
                search_code = getattr(search_error, "code", None)
                if search_code not in {400, 403, 404, 429}:
                    raise
                response = client.models.generate_content(
                    model=model,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        system_instruction=AGRONOMY_SYSTEM_INSTRUCTION.replace("Always respond in English; do not translate the question or answer.", f"Always respond in {LANGUAGES[answer_language]}, using its native script. Keep crop names, units, chemical names and numeric values accurate."),
                        temperature=0.45,
                        max_output_tokens=1800,
                    ),
                )
        answer = (response.text or "").strip()
        web_sources: list[dict[str, str]] = []
        candidates = getattr(response, "candidates", None) or []
        metadata = getattr(candidates[0], "grounding_metadata", None) if candidates else None
        for chunk in (getattr(metadata, "grounding_chunks", None) or []):
            web = getattr(chunk, "web", None)
            uri = getattr(web, "uri", None) if web else None
            title = getattr(web, "title", None) if web else None
            if uri and title and uri.startswith(("https://", "http://")):
                web_sources.append({"title": title, "url": uri})
    except Exception as error:
        code = getattr(error, "code", None)
        if code in {401, 403}:
            raise AdvisorGenerationError("Gemini rejected the API key. Check GEMINI_API_KEY in backend/.env.", status_code=503) from error
        if code == 404:
            raise AdvisorGenerationError(f"Gemini model '{model}' is unavailable. Update GEMINI_GENERATION_MODEL in backend/.env.", status_code=503) from error
        if code == 429:
            raise AdvisorGenerationError("Gemini quota or rate limit reached. Check the API project's quota and billing.", status_code=429) from error
        if code == 503:
            raise AdvisorGenerationError("Gemini is temporarily unavailable. Please retry shortly.", status_code=503) from error
        raise AdvisorGenerationError("Gemini could not generate an answer. Check backend logs and the API connection.") from error
    if not answer:
        raise AdvisorGenerationError("Gemini returned an empty answer. Please retry.")
    return answer, web_sources
