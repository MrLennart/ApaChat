from ..MCPClient.MCPClient import MCPClient
from ..LLM.LLM import LLM
from urllib.parse import urlparse

class Agent:
    def __init__(self):
        self.mcp = {}
        self.LLM = None
        self.connected_status = False
        self.history = []

    async def get_response(self, user_input:str, temperature=0, max_tokens=2000):
        if not self.LLM:
            raise RuntimeError("LLM client is not connected. Please connect to an LLM first.")
    # Prepend the tool prompt to the messages
        self.history.append({"role": "user", "content": user_input})
        try:
            self.LLM.tools= self.active_tools()
            response = self.LLM.chat_completion(
                messages=self.history,
                temperature=temperature,
                max_tokens=max_tokens
            )
            while response.choices[0].message.tool_calls:
                for tool_call in response.choices[0].message.tool_calls:
                    self.history.append({"role":"assistant","tool_calls":[tool_call]})
                    tool_result= await self.handle_tool_call(tool_call.function)
                    print(tool_result)
                    self.history.append({                               # append result message
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "name":tool_call.function.name,
                    "content": str(tool_result)
                })
                response = self.LLM.chat_completion(
                    messages=self.history,
                    temperature=temperature,
                    max_tokens=max_tokens
                )
            reply = response.choices[0].message.content
            self.history.append({"role": "assistant", "content": reply})
            return reply
        except Exception as e:
            raise RuntimeError(f"An error occurred during chat completion: {str(e)}")


    def active_tools(self):
        """Returns all tools labeled as active, with names as server.toolname."""
        active_tools = []
        for server, entry in self.mcp.items():
            for tool in entry.get("tools", []):
                if tool.get("active"):
                    active_tools.append({
                        "type": "function",
                        "function": {
                            "name": f"{server}_{tool['name']}",
                            "description": tool["description"],
                            "parameters": tool["input_schema"]
                        }
                    })
        return active_tools

    async def connect_LLM(self, base_url:str=None, model_name:str=None, api_key:str=None):
        self.LLM = LLM(base_url=base_url, model_name=model_name, api_key=api_key)
        try:
            models=self.LLM.list_models()  # Test the connection by listing models
            self.connected_status = True
            model_names = [m.id for m in models if hasattr(m, "id")]
            return model_names
        except Exception as e:
            self.connected_status = False
            raise RuntimeError(f"Error connecting to LLM: {e}")

    async def connect_MCP(self, server_url: str, auth_method: str = "none", token: str = None, oauth_server_url: str = None):
        client = MCPClient()
        parsed = urlparse(server_url)
        host = parsed.hostname.split(".")[-2] or ""
        port = f"{parsed.port}" if parsed.port else ""
        name=f"{host}{port}"
        self.mcp[name] = {"client": client, "connected": False, "tools": []}
        try:
            tools = await client.connect_to_sse_server(server_url, auth_method, token, oauth_server_url)
            mcp_tools = []
            mcp_tools.extend(
                {
                    "name": tool.name,
                    "description": tool.description,
                    "input_schema": tool.inputSchema,
                    "active": False
                }
                for tool in tools
            )
            self.mcp[name]["tools"] = mcp_tools
            self.mcp[name]["connected"] = True
            return self.mcp[name]
        except Exception as e:
            self.mcp[name]["connected"] = False
            raise RuntimeError(f"Error connecting to MCP: {e}")

    async def handle_tool_call(self, tool_call):
        # Extract tool name and arguments from the tool_call
        if "_" in tool_call.name:
            server, tool_name = tool_call.name.split("_", 1)
        else:
            server, tool_name = None, tool_call.name
        tool_args = tool_call.arguments

        if isinstance(tool_args, str):
                try:
                    tool_args = eval(tool_args)  # Convert string to dictionary
                except Exception as e:
                    return f"Invalid arguments format: {tool_args}. Error: {e}"


        if not tool_name:
            return "Tool name is missing in the tool call"
        
        if not self.mcp:
            raise RuntimeError("MCP client is not connected")
        # Check if 'server' is specified and exists in self.mcp (assuming self.mcp is a dict or has a dict attribute)
        if server:
            if server in self.mcp:
                result = await self.mcp[server]["client"].session.call_tool(tool_name, tool_args)
            else:
                return f"Server '{server}' not found in MCP client"


        # Handle the result (if needed)
        if result:
            return (f"Tool '{tool_name}' executed successfully with result: {result}")
        else:
            return (f"Tool '{tool_name}' execution returned no result")


