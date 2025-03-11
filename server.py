import asyncio
import json
import sys
from typing import Any, Dict, Optional

import httpx
from mcp import ClientSession
from mcp.client.sse import sse_client
from mcp.server.fastmcp import FastMCP

# Initialize MCP gateway server
server = FastMCP("mcp-gateway")

REGISTRY_API_URL = "http://localhost:42069"

# Track active service connections
active_connections: Dict[str, ClientSession] = {}


async def fetch_from_registry(
    path: str, params: Optional[Dict[str, str]] = None
) -> Optional[Any]:
    """
    Helper function to fetch data from registry API
    """
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
async def connect_to_service(service_id: str) -> str:
    """Establish a connection to a remote MCP service.

    Creates either a direct connection to an SSE-based MCP server or a logical connection
    to an HTTP API. Required before using any other service-specific tools.

    IMPORTANT: To use the tools on this server, you MUST USE proxy_tool_call.

    Args:
        service_id: The ID of the service to connect to (from discover_services)
    """
    try:
        # Check if already connected
        if service_id in active_connections:
            return f"Already connected to service {service_id}. Use proxy_tool_call to access its tools."

        # Fetch service details from registry
        service = await fetch_from_registry(f"/services/{service_id}")
        if not service:
            return f"Service with ID {service_id} not found."

        # Check transport type
        transport_type = service.get("transport_type", "http")

        if transport_type == "http":
            return (
                f"Connected to HTTP service: {service['name']}\n"
                f"URL: {service['url']}\n"
                f"Use http_request() to interact with this service's API."
            )
        elif transport_type == "sse":
            # Validate SSE URLs
            sse_event_url = service.get("sse_event_url")
            sse_message_url = service.get("sse_message_url")

            if not sse_event_url or not sse_message_url:
                return f"Service is missing required SSE URLs."

            # Create a future to track connection completion
            connection_future = asyncio.Future()

            # Start connection process with the future
            connection_task = asyncio.create_task(
                establish_sse_connection(service_id, sse_event_url, connection_future)
            )

            try:
                # Wait for connection to establish with timeout
                await asyncio.wait_for(connection_future, timeout=15.0)

                return (
                    f"Connected to SSE service: {service['name']}\n"
                    f"Connection successfully established.\n\n"
                    f"IMPORTANT: To use this service's tools, you must call:\n"
                    f'proxy_tool_call({service_id}, "tool_name", {{arguments}})'
                )
            except asyncio.TimeoutError:
                # Connection is taking too long
                return (
                    f"Connection to {service['name']} initiated but taking longer than expected.\n"
                    f"The connection will continue to be established in the background.\n"
                    f"Please try using proxy_tool_call in a few moments."
                )
        else:
            return f"Unsupported transport type: {transport_type}"
    except Exception as e:
        return f"Error connecting to service: {str(e)}"


async def establish_sse_connection(
    service_id: str, event_url: str, connection_future=None
):
    """Establish an SSE connection to a remote MCP server

    Args:
        service_id: The ID of the service to connect to
        event_url: The SSE event URL for the service
        connection_future: Future to complete when connection is established
    """
    try:
        # Create SSE client
        async with sse_client(event_url) as (read, write):
            # Create client session
            async with ClientSession(read, write) as session:
                # Initialize the connection
                await session.initialize()

                # Store the connection
                active_connections[service_id] = session

                # Signal successful connection if future provided
                if connection_future and not connection_future.done():
                    connection_future.set_result(True)

                # Keep the connection alive until the server disconnects
                try:
                    while True:
                        await asyncio.sleep(10)
                        # Optional: add periodic health check here
                except asyncio.CancelledError:
                    # Handle task cancellation gracefully
                    pass
                except Exception as e:
                    print(f"Connection error: {str(e)}", file=sys.stderr)
                finally:
                    # Remove from active connections on disconnect
                    if service_id in active_connections:
                        del active_connections[service_id]
                    print(f"Connection to {service_id} closed", file=sys.stderr)
    except Exception as e:
        print(f"Error in SSE connection to {service_id}: {str(e)}", file=sys.stderr)

        # Signal connection failure if future provided
        if connection_future and not connection_future.done():
            connection_future.set_exception(e)

        # Clean up
        if service_id in active_connections:
            del active_connections[service_id]


@server.tool()
async def proxy_tool_call(
    service_id: str, tool_name: str, arguments: Dict[str, Any]
) -> str:
    """Execute a tool on a connected MCP service.

    Calls a specific tool on the connected service with the provided arguments.
    Must call connect_to_service first.

    Args:
        service_id: The ID of the connected service
        tool_name: The name of the tool to call
        arguments: A dictionary of arguments to pass to the tool
    """
    if service_id not in active_connections:
        return f"Not connected to service {service_id}. Call connect_to_service({service_id}) first."

    session = active_connections[service_id]

    try:
        result = await asyncio.wait_for(
            session.call_tool(tool_name, arguments), timeout=30.0  # 30 second timeout
        )

        # Process the content based on its type
        if isinstance(result.content, list):
            parts = []
            for item in result.content:
                if hasattr(item, "type"):
                    if item.type == "text" and hasattr(item, "text"):
                        parts.append(item.text)
                    elif item.type == "image":
                        parts.append("[Image content]")
                    elif item.type == "resource":
                        parts.append(f"[Resource: {getattr(item, 'uri', 'Unknown')}]")
                    else:
                        parts.append(str(item))
                else:
                    parts.append(str(item))
            content_text = "\n".join(parts)
        else:
            content_text = str(result.content)

        return f"Tool execution result:\n{content_text}"
    except asyncio.TimeoutError:
        return f"Tool call to {tool_name} timed out after 30 seconds"
    except Exception as e:
        return f"Error calling tool: {str(e)}"


@server.tool()
async def list_service_tools(service_id: str) -> str:
    """List all available tools for a connected MCP service.

    Returns detailed information about each tool including name, description,
    and input schema. Must call connect_to_service first.

    Args:
        service_id: The ID of the connected service
    """
    if service_id not in active_connections:
        return f"Not connected to service {service_id}. Call connect_to_service({service_id}) first."

    session = active_connections[service_id]

    try:
        tools_result = await session.list_tools()
        if not tools_result.tools:
            return f"No tools available for service {service_id}."

        result = f"Available tools for service {service_id}:\n\n"

        for tool in tools_result.tools:
            result += f"Name: {tool.name}\n"

            if hasattr(tool, "description") and tool.description:
                result += f"Description: {tool.description}\n"

            # Use inputSchema instead of input_schema
            if hasattr(tool, "inputSchema") and tool.inputSchema:
                result += "Input Schema:\n"
                if isinstance(tool.inputSchema, dict):
                    schema_str = json.dumps(tool.inputSchema, indent=2)
                    result += f"{schema_str}\n"
                else:
                    result += f"{tool.inputSchema}\n"

            result += "\n"

        return result
    except Exception as e:
        return f"Error listing tools: {str(e)}"


@server.tool()
async def discover_services(query: str = "", category: str = "") -> str:
    """
    Discover available MCP services based on search criteria.
    Calling without parameters returns all services.

    IMPORTANT: After discovering a service that matches the user's needs,
    ALWAYS call get_service_details to learn more about it.

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
            result += f"\nNEXT STEP: Call get_service_details({service_id}) to learn more about this service and how to use it."
        elif len(services) > 1:
            result += f"\nNEXT STEP: For a relevant service, call get_service_details(service_id) before attempting to use it."

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

        # Transport information
        transport_type = service.get("transport_type", "http")
        result += f"Transport Type: {transport_type}\n"

        if transport_type == "sse":
            result += (
                f"SSE Event URL: {service.get('sse_event_url', 'Not specified')}\n"
            )
            result += (
                f"SSE Message URL: {service.get('sse_message_url', 'Not specified')}\n"
            )

        if "protocol_version" in service and service["protocol_version"]:
            result += f"Protocol Version: {service['protocol_version']}\n"

        # Rest of the function remains the same...

        # Update the next steps based on transport type
        result += "\n------------------------------------------\n"
        result += f"NEXT STEPS:\n"

        if transport_type == "sse":
            result += f"1. Call connect_to_service({service_id}) to establish an MCP connection\n"
            result += (
                f"2. Call list_service_tools({service_id}) to see available tools\n"
            )
            result += f"3. Use proxy_tool_call({service_id}, tool_name, arguments) to execute tools\n"
        else:
            result += f"1. Analyze the API documentation above to understand the available endpoints\n"
            result += f"2. Use http_request calls to interact with the service\n"
            result += f"   Example: http_request(method=\"GET\", url=\"{service['url'].rstrip('/')}/endpoint?param=value\")\n"

        return result
    except Exception as e:
        return f"Error getting service details: {str(e)}"


@server.tool()
async def list_service_categories() -> str:
    """List all available service categories in the registry.

    Returns a unique, sorted list of all categories used by registered services.
    Useful for discovering what types of services are available.
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

    Performs an HTTP request with the specified parameters and returns the response.
    Primarily used for HTTP-based services rather than SSE-based MCP services.

    Args:
        method: HTTP method (GET, POST, PUT, DELETE, PATCH)
        url: Complete URL to call
        headers: Optional HTTP headers as a dictionary
        params: Optional query parameters as a dictionary
        json_body: Optional JSON request body as a dictionary
        text_body: Optional text request body as a string
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


if __name__ == "__main__":
    print("Starting MCP Gateway Server...", file=sys.stderr)
    server.run(transport="stdio")  # Using stdio for Claude Desktop
