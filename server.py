from mcp.server.fastmcp import FastMCP

from lib.service_registry import ServiceRegistry

registry = ServiceRegistry()
gateway = FastMCP("gateway")


@gateway.tool()
def discover_services(query: str = "", category: str = "") -> str:
    """
    Discover available MCP services.

    Args:
        query: Optional search terms to find relevant services
        category: Optional category to filter services
    """

    if category:
        services = registry.list_services(category=category)
    elif query:
        services = registry.search_services(query)
    else:
        services = registry.list_services()

    if not services:
        return "No matching services found."

    result = "Available services:\n\n"
    for service in services:
        capabilities = ". ".join([c for c, enabled in service.capabilities.items()])
        result += f"ID: {service.id}\n"
        result += f"Name: {service.name}\n"
        result += f"Description: {service.description}\n"
        result += f"Capabilities: {capabilities}\n"
        result += f"Categories: {service.categories}\n"

    return result


@gateway.tool()
def get_service_details(service_id: str) -> str:
    """
    Get detailed information about a specific service.
    """


if __name__ == "__main__":
    gateway.run(transport="stdio")
