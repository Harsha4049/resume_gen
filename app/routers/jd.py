from fastapi import APIRouter

from app.models.schemas import JDParseRequest, JDParseResponse
from app.services.jd_parser import parse_jd
from app.config import settings

router = APIRouter()


@router.post("/parse-jd", response_model=JDParseResponse)
def parse_jd_endpoint(payload: JDParseRequest) -> JDParseResponse:
    jd_provider = settings.llm_provider
    jd_api_key = (
        settings.openai_api_key if jd_provider.lower() == "openai" else settings.anthropic_api_key
    )
    jd_model = (
        settings.openai_model if jd_provider.lower() == "openai" else settings.claude_model
    )
    return parse_jd(
        jd_text=payload.jd_text,
        api_key=jd_api_key,
        model=jd_model,
        use_claude=True,
        provider=jd_provider,
    )
