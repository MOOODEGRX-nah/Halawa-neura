"""
Invoice Schema - Data definitions
"""
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Any

class InvoiceType(Enum):
    DISPATCH = "DISPATCH"
    PLAN = "PLAN"
    EXECUTION = "EXECUTION"
    REVIEW = "REVIEW"
    FIX_REQUEST = "FIX"

class TaskDomain(Enum):
    CODING = "coding"
    WEB = "web"
    GAME = "game"
    DATA = "data"
    ANALYSIS = "analysis"
    CREATIVE = "creative"

@dataclass
class ProjectFile:
    name: str
    language: str
    content: str
    size_bytes: int = 0
    def __post_init__(self):
        if self.size_bytes == 0:
            self.size_bytes = len(self.content.encode("utf-8"))

@dataclass
class Invoice:
    invoice_id: str
    type: InvoiceType
    from_model: str
    to_model: str
    project_id: str
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    summary: str = ""
    domain: TaskDomain = TaskDomain.CODING
    requirements: List[str] = field(default_factory=list)
    constraints: List[str] = field(default_factory=list)
    architecture: Dict[str, Any] = field(default_factory=dict)
    file_structure: List[Dict[str, str]] = field(default_factory=list)
    files: List[ProjectFile] = field(default_factory=list)
    grade: str = ""
    verdict: str = ""
    issues: List[Dict[str, str]] = field(default_factory=list)
    raw_text: str = ""
    generation_time_s: float = 0.0
