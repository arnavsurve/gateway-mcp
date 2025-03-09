import asyncio

from mcp.server.fastmcp import Context, FastMCP

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

    Args:
        service_id: ID of the service to get details for
    """

    service = registry.get_service(service_id)
    if not service:
        return f"Service with ID {service_id} not found."

    # Format service details
    result = f"Service: {service.name}\n\n"
    result += f"ID: {service.id}\n"
    result += f"Description: {service.description}"
    result += f"URL: {service.url}"

    # Capabilities
    result += "Capabilities:\n"
    for cap, enabled in service.capabilities.items():
        result += f"- {cap}: {"enabled" if enabled else "disabled"}\n"

    # Categories
    if service.metadata:
        result += "\nMetadata:\n"
        for key, value in service.metadata.items():
            result += f"- {key}: {value}\n"

    return result


@gateway.tool()
async def connect_to_service(service_id: str, ctx: Context) -> str:
    """
    Establish a connection to a service and get its capabilities.

    Args:
        service_id: ID of the service to connect to
    """

    service = registry.get_service(service_id)
    if not service:
        return f"Service with ID {service_id} not found."

    try:
        # TODO: use MCP client to connect
        # for now we simulate
        await asyncio.sleep(1)

        return f"Successfully connected to {service.name}. Ready to use service capabilities."
    except Exception as e:
        return f"Failed to connect to service: {str(e)}"


if __name__ == "__main__":
    gateway.run(transport="stdio")
