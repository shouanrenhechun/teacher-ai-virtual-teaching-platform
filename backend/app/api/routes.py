from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..models import TrainingScenario, VirtualStudent
from ..schemas import TrainingScenarioRead, VirtualStudentRead
from .deps import db_session


router = APIRouter(prefix="/api", tags=["core-data"])


@router.get("/scenarios", response_model=list[TrainingScenarioRead])
def list_scenarios(db: Session = Depends(db_session)) -> list[TrainingScenario]:
    statement = select(TrainingScenario).order_by(TrainingScenario.id)
    return list(db.scalars(statement).all())


@router.get("/scenarios/{scenario_id}", response_model=TrainingScenarioRead)
def get_scenario(scenario_id: int, db: Session = Depends(db_session)) -> TrainingScenario:
    scenario = db.get(TrainingScenario, scenario_id)
    if scenario is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="教学实训场景不存在")
    return scenario


@router.get("/virtual-students", response_model=list[VirtualStudentRead])
def list_virtual_students(db: Session = Depends(db_session)) -> list[VirtualStudent]:
    statement = (
        select(VirtualStudent)
        .options(
            selectinload(VirtualStudent.knowledge_states),
        )
        .order_by(VirtualStudent.id)
    )
    return list(db.scalars(statement).all())


@router.get("/virtual-students/{student_id}", response_model=VirtualStudentRead)
def get_virtual_student(student_id: int, db: Session = Depends(db_session)) -> VirtualStudent:
    statement = (
        select(VirtualStudent)
        .where(VirtualStudent.id == student_id)
        .options(
            selectinload(VirtualStudent.knowledge_states),
        )
    )
    student = db.scalar(statement)
    if student is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="虚拟学生不存在")
    return student
