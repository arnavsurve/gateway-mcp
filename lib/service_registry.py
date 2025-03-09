import json
import os
import sys
import time
from typing import Dict, List, Optional

from mcp_service import MCPService

# TODO: migrate from on disk JSON registry to postgres


class ServiceRegistry:
    """Registry for MCP services with persistence"""

    def __init__(self, storage_path: str = "mcp_registry.json"):
        self.storage_path = storage_path
        self.services: Dict[str, MCPService] = {}
        self._load()

    def _load(self):
        """Load registry from disk"""
        if os.path.exists(self.storage_path):
            try:
                with open(self.storage_path, "r") as f:
                    data = json.load(f)
                    for service_data in data:
                        service = MCPService.from_dict(service_data)
                        self.services[service.id] = service
            except Exception as e:
                print(f"Error loading registry: {e}", file=sys.stderr)

    def _save(self):
        """Save registry to disk"""
        try:
            with open(self.storage_path, "w") as f:
                json.dump([s.to_dict() for s in self.services.values()], f, indent=2)
        except Exception as e:
            print(f"Error saving registry: {e}", file=sys.stderr)

    def register_service(self, service: MCPService) -> bool:
        """Register a new service or update existing one"""
        existing = self.services.get(service.id)
        if existing:
            # Update existing service
            service.created_at = existing.created_at  # Preserve creation time
            service.last_seen = time.time()

        self.services[service.id] = service
        self._save()
        return True

    def unregister_service(self, service_id: str) -> bool:
        """Remove a service from the registry"""
        if service_id in self.services:
            del self.services[service_id]
            self._save()
            return True
        return False

    def get_service(self, service_id: str) -> Optional[MCPService]:
        """Get a service by ID"""
        return self.services.get(service_id)

    def list_services(self, category: Optional[str] = None) -> List[MCPService]:
        """List all services, optionally filtered by category"""
        if category:
            return [s for s in self.services.values() if category in s.categories]
        return list(self.services.values())

    def search_services(self, query: str) -> List[MCPService]:
        """Search services by name or description"""
        query = query.lower()
        return [
            s
            for s in self.services.values()
            if query in s.name.lower() or query in s.description.lower()
        ]

    def heartbeat(self, service_id: str) -> bool:
        """Update last_seen timestamp for a service"""
        if service_id in self.services:
            self.services[service_id].last_seen = time.time()
            self._save()
            return True
        return False

    def prune_inactive(self, max_age_seconds: int = 3600) -> int:
        """Remove services that haven't sent a heartbeat recently"""
        now = time.time()
        inactive_ids = [
            sid
            for sid, service in self.services.items()
            if now - service.last_seen > max_age_seconds
        ]

        for sid in inactive_ids:
            del self.services[sid]

        if inactive_ids:
            self._save()

        return len(inactive_ids)
