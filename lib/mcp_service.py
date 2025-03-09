import time
from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class MCPService:
    """Represents a registered MCP service"""

    id: str
    name: str
    description: str
    url: str
    capabilities: Dict[str, bool]
    categories: List[str]
    created_at: float = field(default_factory=time.time)
    last_seen: float = field(default_factory=time.time)
    metadata: Dict = field(default_factory=dict)

    def to_dict(self) -> Dict:
        """Convert to dictionary for serialization"""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "url": self.url,
            "capabilities": self.capabilities,
            "categories": self.categories,
            "created_at": self.created_at,
            "last_seen": self.last_seen,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "MCPService":
        """Create from dictionary after deserialization"""
        return cls(
            id=data["id"],
            name=data["name"],
            description=data["description"],
            url=data["url"],
            capabilities=data["capabilities"],
            categories=data["categories"],
            created_at=data.get("created_at", time.time()),
            last_seen=data.get("last_seen", time.time()),
            metadata=data.get("metadata", {}),
        )
