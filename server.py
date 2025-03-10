import json
import sys
from typing import Any, Dict, List, Optional

import httpx
from mcp.server.fastmcp import FastMCP

# Initialize MCP gateway server
server = FastMCP("mcp-gateway")

REGISTRY_API_URL = "http://localhost:42069"


async def fetch_from_registry(
    path: str, params: Optional[Dict[str, str]] = None
) -> Optional[Any]:
    """Helper function to fetch data from registry API"""
    url = ""
    try:
        async with httpx.AsyncClient() as client:
            url = f"{REGISTRY_API_URL}{path}"
            response = await client.get(url, params=params)
            response.raise_for_status()
            return response.json()
    except Exception as e:
        print(f"Error fetching from registry: {str(e)} (URL: {url})", file=sys.stderr)
        return None


@server.tool()
async def discover_services(query: str = "", category: str = "") -> str:
    """Discover available MCP services based on search criteria.

    IMPORTANT: After discovering a service that matches the user's needs,
    ALWAYS call get_service_details to learn more about it, then
    ALWAYS call get_service_api to understand how to use it properly.

    Args:
        query: Optional search terms to find relevant services
        category: Optional category to filter services
    """
    try:
        if query:
            services = await fetch_from_registry("/services/search", {"q": query})
        elif category:
            services = await fetch_from_registry("/services", {"category": category})
        else:
            # Updated to match Go API endpoint
            services = await fetch_from_registry("/services")

        if not services or len(services) == 0:
            return "No matching services found."

        # Format results for readability
        result = "Available Services:\n\n"
        for service in services:
            capabilities = ", ".join(
                [name for name, enabled in service["capabilities"].items() if enabled]
            )
            result += f"ID: {service['id']}\n"
            result += f"Name: {service['name']}\n"
            result += f"Description: {service['description']}\n"
            result += f"URL: {service['url']}\n"
            result += f"Capabilities: {capabilities}\n"
            result += f"Categories: {', '.join(service['categories'])}\n\n"

        if len(services) == 1:
            service_id = services[0]["id"]
            result += f"\nNEXT STEP: Call get_service_details({service_id}) to learn more about this service, then get_service_api({service_id}) to understand how to use it."
        elif len(services) > 1:
            result += f"\nNEXT STEP: For a relevant service, call get_service_details(service_id) followed by get_service_api(service_id) before attempting to use it."

        return result
    except Exception as e:
        return f"Error discovering services: {str(e)}"


@server.tool()
async def get_service_details(service_id: str) -> str:
    """Get detailed information about a specific service.

    This includes API documentation on how to interact with the service

    Args:
        service_id: The ID of the service to get details for
    """
    try:
        service = await fetch_from_registry(f"/services/{service_id}")
        if not service:
            return f"Service with ID {service_id} not found."

        # Format service details
        result = f"Service: {service['name']}\n\n"
        result += f"ID: {service['id']}\n"
        result += f"Description: {service['description']}\n"
        result += f"URL: {service['url']}\n"

        # Capabilities
        result += "Capabilities:\n"
        for name, enabled in service["capabilities"].items():
            result += f"- {name}: {'✓' if enabled else '✗'}\n"

        # Categories
        result += f"Categories: {', '.join(service['categories'])}\n"

        # Metadata
        if service["metadata"]:
            result += "\nMetadata:\n"
            for key, value in service["metadata"].items():
                result += f"- {key}: {value}\n"

        # API Documentation
        if "api_docs" in service and service["api_docs"]:
            result += f"API Documentation:\n"
            result += "------------------\n"
            result += f"{service['api_docs']}"

        # Determine if this is an MCP Server or an HTTP API
        is_mcp_server = service.get("capabilities", {}).get("tools", False)

        result += "\n------------------------------------------\n"
        result += f"NEXT STEPS:\n"
        if is_mcp_server:
            result += f"1. Call connect_to_service({service_id}) to establish an MCP connection\n"
            result += f"2. Once connected, you'll be able to use the tools provided by this MCP server\n"
        else:
            result += f"1. Analyze the API documentation above to understand the available endpoints\n"
            result += f"2. Use one or subsequent http_request calls to interact with the service by constructing appropriate requests\n"
            result += f"   Example: http_request(method=\"GET\", url=\"{service['url'].rstrip('/')}/endpoint?param=value\")\n"

        return result
    except Exception as e:
        return f"Error getting service details: {str(e)}"


# @server.tool()
# async def connect_to_service(service_id: str) -> str:
#     """Establish a connection to a remote MCP service.
#
#     Args:
#         service_id: The ID of the service to connect to
#     """
#     try:
#         service = await fetch_from_registry(f"/services/{service_id}")
#         if not service:
#             return f"Service with ID {service_id} not found."
#
#         # In a full implementation, we would establish an SSE connection
#         # to the remote MCP server and proxy requests through it
#
#         # For the MVP, we'll return information about what would happen
#         return (
#             f"Would connect to service: {service['name']}\n"
#             f"URL: {service['url']}\n"
#             f"This would establish an SSE connection to the service and allow "
#             f"you to use its tools and resources.\n\n"
#             f"In a future version, this will actually establish the connection."
#         )
#     except Exception as e:
#         return f"Error connecting to service: {str(e)}"


@server.tool()
async def list_service_categories() -> str:
    """
    List all available service categories in the registry.
    """

    try:
        # Fetch all services from the updated endpoint
        services = await fetch_from_registry("/services")
        if not services:
            return "No services found in the registry."

        # Extract all categories
        all_categories = set()
        for service in services:
            for category in service["categories"]:
                all_categories.add(category)

        # Format the result
        categories_list = sorted(list(all_categories))
        if not categories_list:
            return "No categories found."

        result = "Available service categories:\n\n"
        for category in categories_list:
            result += f"- {category}\n"

        return result
    except Exception as e:
        return f"Error listing categories: {str(e)}"


@server.tool()
async def http_request(
    method: str,
    url: str,
    headers: Dict[str, str] = None,
    params: Dict[str, Any] = None,
    json_body: Dict[str, Any] = None,
    text_body: str = None,
) -> str:
    """Execute an HTTP request to a remote API.

    Args:
        method: HTTP method (GET, POST, PUT, DELETE, PATCH)
        url: Full URL to call
        headers: Optional HTTP headers
        params: Optional query parameters
        json_body: Optional JSON request body
        text_body: Optional text request body
    """
    method = method.upper()
    if method not in ["GET", "POST", "PUT", "DELETE", "PATCH"]:
        return f"Unsupported HTTP method: {method}"

    try:
        async with httpx.AsyncClient() as client:
            response = await client.request(
                method=method,
                url=url,
                headers=headers,
                params=params,
                json=json_body,
                content=text_body,
                timeout=30.0,
            )

            # Try to parse response as JSON
            try:
                body = response.json()
                body_str = json.dumps(body, indent=2)
            except Exception:
                body_str = response.text

            return f"HTTP Response:\nStatus: {response.status_code}\nBody: {body_str}"
    except Exception as e:
        return f"Error making HTTP request: {str(e)}"


# @server.tool()
# async def register_service(
#     name: str,
#     description: str,
#     url: str,
#     capabilities: Dict[str, bool],
#     categories: List[str],
#     metadata: Dict[str, str] = {},
# ) -> str:
#     """Register a new MCP service with the registry.
#
#     Args:
#         name: Human-readable name of the service
#         description: Description of what the service does
#         url: URL where the service can be accessed
#         capabilities: Map of service capabilities (tools, resources, prompts)
#         categories: List of categories this service belongs to
#         metadata: Optional additional information about the service
#     """
#     try:
#         # Create registration payload
#         payload = {
#             "name": name,
#             "description": description,
#             "url": url,
#             "capabilities": capabilities,
#             "categories": categories,
#             "metadata": metadata,
#         }
#
#         # Submit registration request
#         async with httpx.AsyncClient() as client:
#             response = await client.post(f"{REGISTRY_API_URL}/services", json=payload)
#
#             if response.status_code == 201:
#                 service = response.json()
#                 return f"Service registered successfully!\nID: {service['id']}\nName: {service['name']}"
#             else:
#                 return f"Failed to register service: {response.text}"
#     except Exception as e:
#         return f"Error registering service: {str(e)}"
#
#
# @server.tool()
# async def unregister_service(service_id: str) -> str:
#     """Remove a service from the registry.
#
#     Args:
#         service_id: The ID of the service to unregister
#     """
#     try:
#         async with httpx.AsyncClient() as client:
#             response = await client.delete(f"{REGISTRY_API_URL}/services/{service_id}")
#
#             if response.status_code == 200:
#                 return f"Service {service_id} has been unregistered."
#             else:
#                 return f"Failed to unregister service: {response.text}"
#     except Exception as e:
#         return f"Error unregistering service: {str(e)}"


if __name__ == "__main__":
    print("Starting MCP Gateway Server...", file=sys.stderr)
    server.run(transport="stdio")  # Using stdio for Claude Desktop
