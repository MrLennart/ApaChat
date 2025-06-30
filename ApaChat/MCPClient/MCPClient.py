import base64
from typing import Optional
import logging
from mcp import ClientSession
from contextlib import AsyncExitStack
from mcp.client.sse import sse_client
import requests
import traceback




logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
class MCPClient:
    def __init__(self):
        # Initialize session and client objects
        self.session: Optional[ClientSession] = None
        self.exit_stack = AsyncExitStack()
        self.status = "Not connected"
        self._streams_context = None
        self._session_context = None

    async def connect_to_sse_server(self, server_url: str, auth_method: str = "none", token: str = None,oauth_server_url: str = None):
        """Connect to an MCP server running with SSE transport using specified auth type (oauth, bearer and none are supported)"""
        # Store the context managers so they stay alive

        await self.cleanup()  # Ensure any previous connections are cleaned up
        headers = {}
        if auth_method.lower() == "bearer" and token:
            headers={"Authorization": f"Bearer {token}"}
        elif auth_method.lower() == "oauth" and token:
            headers={"Authorization": get_token(oauth_server_url=oauth_server_url, creds=token)}
        # No headers for "none"
        try:
            self._streams_context = sse_client(
                url=server_url,
                headers=headers
            )
            streams = await self._streams_context.__aenter__()

            self._session_context = ClientSession(*streams)
            self.session: ClientSession = await self._session_context.__aenter__()

            # Initialize
            await self.session.initialize()

            # List available tools to verify connection
            logger.info("Initialized SSE client with Bearer authentication...")
            response = await self.session.list_tools()
            logger.info(f"Recieved {len(response.tools)} tools from the server.")
            self.status = "Connected"
            return response.tools
        except Exception as e:
            logger.error(f"Failed to connect to SSE server: {e}")
            traceback.print_exc()
    # If it's a TaskGroup error, print sub-exceptions
            if hasattr(e, 'exceptions'):
                for sub in e.exceptions:
                    logger.error(f"Sub-exception: {sub}")
                    traceback.print_exception(type(sub), sub, sub.__traceback__)
    
            self.status = "Connection failed"
            raise RuntimeError(f"Failed to connect to SSE server: {e}")

    async def cleanup(self):
        """Properly clean up the session and streams"""
        if self._session_context:
            await self._session_context.__aexit__(None, None, None)
        if self._streams_context:
            await self._streams_context.__aexit__(None, None, None)
        self.status = "Not Connected"
        return None

    async def call_tool(self, tool_name: str, tool_args: dict):
        try:
            result = await self.session.call_tool(tool_name, tool_args)
            # Handle the result (if needed)
            if result:
                return (f"Tool '{tool_name}' executed successfully with result: {result}")
            else:
                return (f"Tool '{tool_name}' execution returned no result")
        except Exception as e:
            logger.error(f"Error calling tool '{tool_name}': {e}")  
            return f"Error calling tool '{tool_name}': {e}"
        
    async def list_tools(self):
        """List available tools from the MCP server"""
        try:
            response = await self.session.list_tools()
            tools = response.tools
            return tools
        except Exception as e:
            logger.error(f"Error listing tools: {e}")
            self.status = "Connection failed"
            raise RuntimeError(f"Failed to list tools: {e}")


def get_token(oauth_server_url:str=None,creds=None):
    try:
        creds=creds.encode("ascii")
        creds=base64.b64encode(creds)
        headers={"Authorization": f"Basic {creds.decode("ascii")}","Content-Type":"application/x-www-form-urlencoded"}
        params={"grant_type":"client_credentials"}
        token=requests.post(oauth_server_url,data=params,headers=headers)
        token=token.json()['access_token']
        authorization = f'Bearer {token}'
        return authorization
    except Exception as e:
        logger.error(f"Error trying to get OAuth token: {e}")
        raise RuntimeError(f"Failed to get OAuth token: {e}")

