from fastapi import APIRouter

from app.models.schemas import JDParseRequest, JDParseResponse
from app.services.jd_parser import parse_jd
from app.config import settings

router = APIRouter()


@router.post("/parse-jd", response_model=JDParseResponse)
def parse_jd_endpoint(payload: JDParseRequest) -> JDParseResponse:
    return parse_jd(
        jd_text=payload.jd_text,
        api_key=settings.anthropic_api_key,
        model=settings.claude_model,
        use_claude=True,
    )
