from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel
from typing import Optional, Dict, Any

from backend.services.ai_service import evaluate_cv_round_1, evaluate_cv_round_2
from backend.config import require_admin

router = APIRouter()

class EvaluateRequest(BaseModel):
    cv_text: str
    jd_text: str
    criteria: str
    round: int
    answers: Optional[str] = None

@router.post("/evaluate")
async def evaluate_cv(request: EvaluateRequest, x_admin_key: str = Header(None)) -> Dict[str, Any]:
    """
    Stateless endpoint for PAI Engine evaluation.
    round 1: Evaluate CV against JD and criteria. Returns NEED_INFO with questions, or COMPLETED with score.
    round 2: Evaluate CV + Answers against JD and criteria. Returns COMPLETED with final score.
    """
    require_admin(x_admin_key)
    
    if request.round not in (1, 2):
        raise HTTPException(status_code=400, detail="Round must be 1 or 2.")
        
    if request.round == 1:
        try:
            result = await evaluate_cv_round_1(request.cv_text, request.jd_text, request.criteria)
            return result
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
            
    elif request.round == 2:
        if not request.answers:
            raise HTTPException(status_code=400, detail="Answers are required for round 2.")
        try:
            result = await evaluate_cv_round_2(request.cv_text, request.jd_text, request.criteria, request.answers)
            return result
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
