from fastapi import APIRouter
from app.modules.network_simulate.service import apply_network_config
from app.modules.network_simulate.models import NetworkConfig
from app.core.state import runs

router = APIRouter()

@router.post("/apply")
def apply_network(config: NetworkConfig):
    if not config.enabled:
        return {"status": "disabled"}

    # Persist config so test_runner can fetch it by run_id
    if config.run_id:
        runs[config.run_id] = {"network_config": config.dict()}

    result = apply_network_config(config.dict())
    return {"status": "applied", "details": result}

@router.get("/config/{run_id}")
def get_network_config(run_id: str):
    run = runs.get(run_id)
    if not run:
        return {"status": "not_found"}

    return {
        "status": "success",
        "network_config": run.get("network_config")
    }