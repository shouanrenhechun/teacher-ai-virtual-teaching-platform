from fastapi import APIRouter, Depends, HTTPException, status

from ..schemas.llm import LLMRespondRequest, LLMRespondResponse
from ..services.llm import LLMClient, LLMContext, build_llm_client
from ..services.llm.base import LLMConfigurationError, LLMServiceError
from ..services.virtual_student import stable_profile_id


router = APIRouter(prefix="/api/llm", tags=["llm"])


def llm_client_dependency() -> LLMClient:
    try:
        return build_llm_client()
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="LLM 配置无效，请检查 LLM_PROVIDER",
        ) from exc


@router.post("/respond", response_model=LLMRespondResponse)
def respond_to_teacher(
    request: LLMRespondRequest,
    client: LLMClient = Depends(llm_client_dependency),
) -> LLMRespondResponse:
    try:
        student_text = client.respond(
            request.teacher_text,
            LLMContext(
                student_name=request.student_name,
                topic=request.scenario_topic,
                student_profile_id=stable_profile_id(request.student_name),
            ),
        )
    except LLMConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except LLMServiceError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="LLM 配置无效，请检查后端环境变量",
        ) from exc

    return LLMRespondResponse(provider=client.provider, student_text=student_text)
