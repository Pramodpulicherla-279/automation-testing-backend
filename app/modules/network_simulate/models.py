
from pydantic import BaseModel
from typing import Optional

class NetworkConfig(BaseModel):
    enabled: bool
    networkType: str
    download: float
    upload: float
    latency: int
    packetLoss: float
    jitter: int
    run_id: Optional[str] = None
