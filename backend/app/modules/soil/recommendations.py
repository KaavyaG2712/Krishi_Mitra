"""Conservative structured guidance: no inferred measurements or fertilizer doses."""
from app.modules.soil.models import PARAMETERS, SoilProfile


def recommend(profile: SoilProfile) -> dict:
    missing = [name for key, (name, _) in PARAMETERS.items() if key not in profile.parameters]
    steps = ["Keep this report and discuss crop, season and irrigation with your local KVK or agricultural officer.",
             "Use a current laboratory soil test and locally approved crop recommendations before deciding fertilizer quantities."]
    if missing:
        steps.insert(0, "Some values are missing. Leave them unknown; a missing value does not mean zero.")
    return {"status": "needs_local_agronomy_review", "engine_version": "soil-guidance-1",
            "summary": "Your soil values are ready to discuss with an agricultural expert.",
            "steps": steps, "missing_parameters": missing, "fertilizer_dosages": [],
            "limitations": ["No Low/Medium/High rating is assigned without a matching test method and validated local thresholds.",
                            "An area sample may not describe your field or its current condition."],
            "source_url": "https://www.nic.gov.in/project/soil-health-card-portal/"}


def explain(profile: SoilProfile) -> str:
    result = recommend(profile)
    values = "; ".join(f"{PARAMETERS[key][0]}: {m.value:g} {m.unit}" for key, m in profile.parameters.items())
    return f"Soil information ({profile.source_type.value}): {values}.\n" + "\n".join(result["steps"] + result["limitations"])
