import tkinter as tk
from tkinter import messagebox
import tkinter.ttk as ttk
import asyncio
from ..Agent.Agent import Agent
from ..Agent.Agent import url_to_name
from ..LLM.LLM import available_LLM_providers

from tkhtmlview import HTMLScrolledText
from markdown import markdown
import getpass






try:
    import keyring
except ImportError:
    keyring = None
    print("Keyring module not available, credentials saving disabled")
import json

class AsyncTk(tk.Tk):
    def __init__(self, agent):
        super().__init__()
        self._credential_cache = {}
        self.user=getpass.getuser()

        self.agent = agent
        self.title("ApaChat")
        self.geometry("600x400")

        self.status_label = tk.Label(self, text="Connecting...", fg="blue")
        self.status_label.pack(side='top', fill='x')

        self.chat_display = HTMLScrolledText(self, background="#1e1e1e", foreground="#dddddd", borderwidth=0)

        self.chat_display.pack(expand=True, fill='both')

        self.chat_history_html = ""


        self.entry = tk.Entry(self)
        self.entry.pack(fill='x')
        self.entry.bind("<Return>", lambda e: self.send_message())

        self.menu = tk.Menu(self)
        self.config(menu=self.menu)
        self.conn_menu = tk.Menu(self.menu, tearoff=0)
        self.conn_menu.add_command(label="Connect to LLM", command=self.open_llm_dialog)
        self.conn_menu.add_command(label="Configure MCP", command=self.open_mcp_dialog)
        self.menu.add_cascade(label="Connections", menu=self.conn_menu)

        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.loop = asyncio.get_event_loop()
        self.after(100, self.poll_loop)

        self.disable_ui()
        self.after(0, lambda: asyncio.ensure_future(self.initialize_connections()))

    def get_cached_password(self, key):
        # Check in-memory cache first
        print(self._credential_cache)
        if self._credential_cache and key in self._credential_cache:
            return self._credential_cache[key]
        if keyring:
            try:
                data = keyring.get_password("ApaChat", self.user)
                if data is None:
                    return None
                # Try to load JSON from keyring
                self._credential_cache = json.loads(data)

                return self._credential_cache.get(key)
            except Exception as e:
                print(f"Keyring error for {key}: {e}")
                return None
        return None

    def set_cached_password(self, key, value):
        print(f"Setting cached password for {key}")
        if not keyring:
            return
        try:
            # Load existing cache from keyring if not present
            if not self._credential_cache:
                data = keyring.get_password("ApaChat", self.user)
                if data:
                    self._credential_cache = json.loads(data)
                else:
                    self._credential_cache = {}
            self._credential_cache[key] = value
            keyring.set_password("ApaChat", self.user, json.dumps(self._credential_cache))
        except Exception as e:
            print(f"Failed to save {key} to keyring: {e}")

    def disable_ui(self):
        self.entry.config(state='disabled')
        self.conn_menu.entryconfig("Connect to LLM", state="disabled")
        self.conn_menu.entryconfig("Configure MCP", state="disabled")

    def enable_ui(self):
        self.entry.config(state='normal')
        self.conn_menu.entryconfig("Connect to LLM", state="normal")
        self.conn_menu.entryconfig("Configure MCP", state="normal")
        self.status_label.config(text="Connected", fg="green")

    async def initialize_connections(self):
        try:
            await self.auto_connect_saved()
        finally:
            self.enable_ui()

    async def auto_connect_saved(self):
        llm_data = None
        try:
            llm_data = self.get_cached_password( "LLM")
        except Exception as e:
            print(f"Error accessing saved LLM credentials: {e}")
        if llm_data:
            try:
                base = llm_data.get("base_url")
                api_key = llm_data.get("api_key")
                model = llm_data.get("model")
                models = await self.agent.connect_LLM(base_url=base, api_key=api_key)
                if models:
                    chosen_model = model if model in models else models[0]
                    self.agent.LLM.model = chosen_model
                    self.agent.selected_model = chosen_model
                
            except Exception as e:
                print(f"Auto-connect to LLM failed: {e}")
        mcp_list_json = None
        try:
            mcp_list_json = self.get_cached_password( "MCP_list")
        except Exception as e:
            print(f"Error accessing saved MCP list: {e}")
        if mcp_list_json:
            try:
                saved_servers = mcp_list_json
            except Exception as e:
                saved_servers = []
            for url in saved_servers:
                cred_json = None
                try:
                    key_name = f"MCP_{url_to_name(url)}"
                    cred_json = self.get_cached_password( key_name)
                except Exception as e:
                    print(f"Error accessing credentials for MCP {url}: {e}")
                if not cred_json:
                    continue
                data = cred_json
                auth = data.get("auth")
                token = data.get("token")
                oauth_url = data.get("oauth_url")
                server_name = url_to_name(url)
                try:
                    await self.agent.connect_MCP(url, auth, token if token not in [None, ""] else None,
                                                 oauth_url if oauth_url not in [None, ""] else None)
                except Exception as e:
                    print(f"Auto-connect to MCP {url} failed: {e}")
                    self.agent.mcp[server_name] = {
                        "connected": False,
                        "url": url,
                        "auth": auth,
                        "token": token,
                        "oauth_url": oauth_url,
                        "tools": []
                    }
                try:
                    # Nach dem Laden der Credentials und dem Verbindungsaufbau:
                    active_tools = data.get("active_tools", [])
                    for tool in self.agent.mcp[server_name]["tools"]:
                        try:
                            tool["active"] = tool["name"] in active_tools
                        except KeyError:
                            print(f"Tool {tool} missing 'name' key, skipping activation update")
                except Exception as e:
                    print(f"Error updating active tools for MCP {url}: {e}")

    def save_active_tools_for_server(self, server_name):
        if not keyring:
            return
        key_name = f"MCP_{server_name}"
        cred_json = self.get_cached_password(key_name)
        if cred_json:
            data = cred_json
            tools = self.agent.mcp[server_name]["tools"]
            data["active_tools"] = [tool["name"] for tool in tools if tool.get("active")]
            self.set_cached_password(key_name, data)    

    def poll_loop(self):
        try:
            self.loop.call_soon(self.loop.stop)
            self.loop.run_forever()
        finally:
            self.after(100, self.poll_loop)

    def send_message(self):
        msg = self.entry.get()
        if not msg.strip():
            return
        self.entry.delete(0, tk.END)
        self.append_chat("User", msg)
        asyncio.ensure_future(self.handle_response(msg))

    async def handle_response(self, msg):
        try:
            response = await self.agent.get_response(msg)
        except Exception as e:
            response = f"[Error: {e}]"
        self.append_chat("Agent", response)


    def append_chat(self, sender, msg):
        # Ensure chat history exists
        if not hasattr(self, "chat_history_html"):
            self.chat_history_html = ""

        # Inline style applied to each message wrapper
        style = 'style="color:#dddddd; font-family:Arial, sans-serif;"'
        label_style = 'style="color:#ffffff;"'

        if sender == "User":
            safe_text = msg.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            new_html = f'<p {style}><b {label_style}>{sender}:</b> {safe_text}</p>'
        else:
            html_content = markdown(msg)
            # Inject style into all <p> tags in the markdown result
            html_content = html_content.replace("<p>", f"<p {style}>")
            html_content = html_content.replace("<li>", f"<li {style}>")
            new_html = f'<p {style}><b {label_style}>{sender}:</b></p>{html_content}'

        self.chat_history_html += new_html
        self.chat_display.set_html(self.chat_history_html)
        self.chat_display.yview(tk.END)



    def open_llm_dialog(self):
        win = tk.Toplevel(self)
        win.title("Connect to LLM")
        win.geometry("400x300")
        tk.Label(win, text="Base URL").pack()

        # Get example provider names and URLs
        providers = available_LLM_providers()
        provider_names = [entry["name"] for entry in providers.values()]
        name_to_url = {entry["name"]: entry["base_url"] for entry in providers.values()}

        url_var = tk.StringVar()
        url_entry = ttk.Combobox(win, values=provider_names)
        url_entry.pack(fill='x', padx=5)
        url_entry.set("")  # Start empty

        def on_provider_selected(event):
            name = url_entry.get()
            if name in name_to_url:
                url_var.set(name_to_url[name])
                # Optionally, show the URL in the combobox itself:
                url_entry.set(name_to_url[name])

        url_entry.bind("<<ComboboxSelected>>", on_provider_selected)

        # If you want to allow manual URL entry, add a separate Entry for the URL:
        # Or, you can use url_var as the textvariable for url_entry, but then the dropdown will show URLs, not names.

        tk.Label(win, text="API Key").pack()
        key_entry = tk.Entry(win, show='*')
        key_entry.pack(fill='x', padx=5)
        save_var = tk.BooleanVar(value=False)
        save_cb = tk.Checkbutton(win, text="Save credentials", variable=save_var)
        save_cb.pack(pady=5)

        output_frame = tk.Frame(win)
        output_frame.pack(fill='both', expand=True)

        connect_btn = tk.Button(win, text="Connect")
        connect_btn.pack(pady=5)

        async def do_connect():
            connect_btn.config(state='disabled')
            url_entry.config(state='disabled')
            key_entry.config(state='disabled')
            save_cb.config(state='disabled')
            try:
                # Use the URL if a name was selected, else use the text as entered
                url = url_entry.get()
                if url in name_to_url:
                    url = name_to_url[url]
                models = await self.agent.connect_LLM(base_url=url, api_key=key_entry.get())
                for widget in output_frame.winfo_children():
                    widget.destroy()
                var = tk.StringVar()
                for model in models:
                    tk.Radiobutton(output_frame, text=model, variable=var, value=model).pack(anchor='w')
                if models:
                    var.set(models[0])
                    self.agent.LLM.model = models[0]
                    self.agent.selected_model = models[0]
                def save_selection():
                    self.agent.selected_model = var.get()
                    self.agent.LLM.model = var.get()
                    if keyring and save_var.get():
                        creds = {
                            "base_url": url,
                            "api_key": key_entry.get(),
                            "model": var.get()
                        }
                        try:
                            self.set_cached_password("LLM", creds)
                        except Exception as e:
                            print(f"Failed to save LLM credentials: {e}")
                    win.destroy()
                win.protocol("WM_DELETE_WINDOW", save_selection)
                tk.Button(win, text="OK", command=save_selection).pack(pady=5)
            except Exception as e:
                messagebox.showerror("Error", str(e))
                connect_btn.config(state='normal')
                url_entry.config(state='normal')
                key_entry.config(state='normal')
                save_cb.config(state='normal')

        connect_btn.config(command=lambda: asyncio.ensure_future(do_connect()))

    def open_mcp_dialog(self):
        win = tk.Toplevel(self)
        win.title("Configure MCP")
        win.geometry("700x600")

        # Section: Add new MCP server
        add_frame = tk.Frame(win)
        add_frame.pack(fill='x')
        tk.Label(add_frame, text="MCP URL").grid(row=0, column=0, sticky='w')
        url_entry = tk.Entry(add_frame, width=40)
        url_entry.grid(row=0, column=1, padx=5, pady=2)
        auth_var = tk.StringVar(value="None")
        tk.Label(add_frame, text="Auth").grid(row=1, column=0, sticky='w')
        auth_menu = tk.OptionMenu(add_frame, auth_var, "None", "Bearer", "OAuth")
        auth_menu.grid(row=1, column=1, sticky='w', pady=2)
        token_label = tk.Label(add_frame, text="Token")
        token_entry = tk.Entry(add_frame, show="*")
        oauth_label = tk.Label(add_frame, text="OAuth URL")
        oauth_entry = tk.Entry(add_frame)
        # Function to show/hide token/oauth fields based on auth selection
        def update_auth_fields(*args):
            token_label.grid_forget()
            token_entry.grid_forget()
            oauth_label.grid_forget()
            oauth_entry.grid_forget()
            if auth_var.get() == "Bearer":
                token_label.grid(row=2, column=0, sticky='w')
                token_entry.grid(row=2, column=1, padx=5, pady=2, sticky='w')
            elif auth_var.get() == "OAuth":
                token_label.grid(row=2, column=0, sticky='w')
                token_entry.grid(row=2, column=1, padx=5, pady=2, sticky='w')
                # Provide placeholder default values for OAuth (if any)
                oauth_label.grid(row=3, column=0, sticky='w')
                oauth_entry.grid(row=3, column=1, padx=5, pady=2, sticky='w')
        auth_var.trace_add("write", update_auth_fields)
        update_auth_fields()  # Initialize fields visibility

        # Save credentials checkbox for MCP
        save_var = tk.BooleanVar(value=False)
        save_cb = tk.Checkbutton(add_frame, text="Save credentials", variable=save_var)
        save_cb.grid(row=4, column=0, columnspan=2, sticky='w', pady=(5,2))

        # Add Server button
        add_btn = tk.Button(add_frame, text="Add Server")
        add_btn.grid(row=5, column=0, columnspan=2, pady=5)

        # Section: List of servers with connection status
        list_label = tk.Label(win, text="Configured Servers:")
        list_label.pack(pady=(10, 0))
        list_frame = tk.Frame(win)
        list_frame.pack(fill='both', expand=True)
        list_scroll = tk.Scrollbar(list_frame, orient="vertical")
        server_listbox = tk.Listbox(list_frame, yscrollcommand=list_scroll.set)
        list_scroll.config(command=server_listbox.yview)
        list_scroll.pack(side="right", fill="y")
        server_listbox.pack(side="left", fill="both", expand=True)

        # Delete Server button
        def delete_selected_server():
            selected = server_listbox.curselection()
            if not selected:
                return
            index = selected[0]
            item_text = server_listbox.get(index)
            server_url = item_text.split(" - ")[0]
            if messagebox.askyesno("Delete Server", f"Are you sure you want to delete {server_url}?"):
                # Remove from agent.mcp
                self.agent.mcp.pop(server_url, None)
                # Remove credentials and list entry from keyring
                if keyring:
                    try:
                        keyring.delete_password("ApaChat", f"MCP_{server_url}")
                        # Load, update and save MCP_list
                        list_json = self.get_cached_password( "MCP_list")
                        if list_json:
                            current_list = json.loads(list_json)
                            if server_url in current_list:
                                current_list.remove(server_url)
                                self.set_cached_password("MCP_list", current_list)
                    except Exception as e:
                        print(f"Failed to delete {server_url} from keyring: {e}")
                refresh_server_list()

        delete_btn = tk.Button(win, text="Delete Selected Server", command=delete_selected_server)
        delete_btn.pack(pady=5)


        # Populate the listbox with current servers from agent.mcp
        def refresh_server_list():
            server_listbox.delete(0, tk.END)
            for url, server in self.agent.mcp.items():
                status_text = "Connected" if server.get("connected") else "Not connected"
                display_text = f"{url} - {status_text}"
                server_listbox.insert(tk.END, display_text)
        refresh_server_list()

        # Define function to open tool dialog for a specific server
        def open_tool_dialog(server_url):
            server_data = self.agent.mcp.get(server_url)
            if not server_data:
                return
            tools = server_data.get("tools", [])
            tool_win = tk.Toplevel(win)
            tool_win.title(f"Tools - {server_url}")
            tool_win.geometry("500x400")
# ...inside open_tool_dialog...
            filter_var = tk.StringVar()
            filter_entry = tk.Entry(tool_win, textvariable=filter_var)
            filter_entry.pack(fill='x', padx=5, pady=5)

            # Add placeholder text "Search"
            filter_entry.insert(0, "Search")
            filter_entry.config(fg='grey')

            def on_focus_in(event):
                if filter_entry.get() == "Search":
                    filter_entry.delete(0, tk.END)
                    filter_entry.config(fg='white')

            def on_focus_out(event):
                if not filter_entry.get():
                    filter_entry.insert(0, "Search")
                    filter_entry.config(fg='grey')

            filter_entry.bind("<FocusIn>", on_focus_in)
            filter_entry.bind("<FocusOut>", on_focus_out)
            canvas = tk.Canvas(tool_win)
            scrollbar = tk.Scrollbar(tool_win, orient="vertical", command=canvas.yview)
            scroll_frame = tk.Frame(canvas)
            scroll_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
            canvas.create_window((0, 0), window=scroll_frame, anchor="nw")
            canvas.configure(yscrollcommand=scrollbar.set)
            canvas.pack(side="left", fill="both", expand=True)
            scrollbar.pack(side="right", fill="y")
            tool_checkboxes = []
            for tool in tools:
                var = tk.BooleanVar(value=tool.get("active", False))
                cb = tk.Checkbutton(scroll_frame, text=tool.get("name", "Unknown"), variable=var)
                cb.var = var
                cb.tool = tool
                def on_toggle(b=cb):
                    b.tool.update({'active': b.var.get()})
                    self.save_active_tools_for_server(server_url)
                cb.config(command=on_toggle)
                cb.pack(anchor='w')
                tool_checkboxes.append(cb)
            # Filter functionality for tools list
            def update_tool_filter(*args):
                keyword = filter_var.get().lower()
                for cb in tool_checkboxes:
                    name = cb.tool.get("name", "").lower() if isinstance(cb.tool, dict) else str(cb.tool).lower()
                    visible = (keyword in name)
                    cb.pack_forget()
                    if visible:
                        cb.pack(anchor='w')
            filter_var.trace_add("write", update_tool_filter)
            def on_close():
                self.save_active_tools_for_server(server_url)
                tool_win.destroy()

            tool_win.protocol("WM_DELETE_WINDOW", on_close)

        # Double-click event on server list to connect or open tools
        def on_server_double_click(event):
            if server_listbox.curselection():
                index = server_listbox.curselection()[0]
                # Extract server URL from the selected list item text (split at " - ")
                item_text = server_listbox.get(index)
                server_url = item_text.split(" - ")[0]
                server_info = self.agent.mcp.get(server_url)
                if not server_info:
                    return
                if server_info.get("connected"):
                    # Already connected: open the tools dialog
                    open_tool_dialog(server_url)
                else:
                    # Not connected: attempt to reconnect using stored credentials
                    # Disable listbox to prevent multiple triggers
                    server_listbox.config(state='disabled')
                    async def reconnect_and_open():
                        try:
                            # Retrieve credentials from keyring if available
                            cred_json = None
                            if keyring:
                                try:
                                    cred_json = self.get_cached_password( f"MCP_{server_url}")
                                except Exception as kr_err:
                                    print(f"Keyring lookup failed for {server_url}: {kr_err}")
                            # Use credentials from stored data or agent.mcp (set during auto_connect_saved if any)
                            auth = server_info.get("auth")
                            token = server_info.get("token")
                            oauth_url = server_info.get("oauth_url")
                            if cred_json:
                                data = json.loads(cred_json)
                                auth = data.get("auth", auth)
                                token = data.get("token", token)
                                oauth_url = data.get("oauth_url", oauth_url)
                            # Attempt to connect
                            await self.agent.connect_MCP(server_url, auth, token if token not in [None, ""] else None,
                                                         oauth_url if oauth_url not in [None, ""] else None)
                            # If successful, update status and open tools
                            server_info = self.agent.mcp.get(server_url, {})
                            server_info["connected"] = True
                            # Refresh list display to show updated status
                            refresh_server_list()
                            # Open tool dialog for this server
                            open_tool_dialog(server_url)
                        except Exception as e:
                            messagebox.showerror("Error", f"Failed to connect to {server_url}:\n{e}")
                        finally:
                            # Re-enable the listbox
                            server_listbox.config(state='normal')
                    asyncio.ensure_future(reconnect_and_open())
        server_listbox.bind('<Double-Button-1>', on_server_double_click)

        async def do_add():
            # Disable add controls while connecting
            add_btn.config(state='disabled')
            url_entry.config(state='disabled')
            auth_menu.config(state='disabled')
            token_entry.config(state='disabled')
            oauth_entry.config(state='disabled')
            save_cb.config(state='disabled')
            try:
                url = url_entry.get()
                auth_method = auth_var.get()
                token_val = token_entry.get() if token_entry.winfo_ismapped() and token_entry.get() != "" else None
                oauth_val = oauth_entry.get() if oauth_entry.winfo_ismapped() and oauth_entry.get() != "" else None
                # Attempt to connect to the new MCP server
                server = await self.agent.connect_MCP(url, auth_method, token_val, oauth_val)
                # On success, `server` is the server data (dict) and self.agent.mcp should be updated
                server_data = self.agent.mcp.get(url, server)  # ensure we have the server dict
                server_data["connected"] = True
                # Save credentials if checked
                if keyring and save_var.get():
                    # Update MCP list in keyring
                    try:
                        current_list = []
                        list_json = self.get_cached_password( "MCP_list")
                        if list_json:
                            current_list = json.loads(list_json)
                        if url not in current_list:
                            current_list.append(url)
                        self.set_cached_password("MCP_list", current_list)
                    except Exception as e:
                        print(f"Failed to update MCP list in keyring: {e}")
                    # Save this server's credentials
                    cred_info = {
                        "url": url,
                        "auth": auth_method,
                        "token": token_val if token_val is not None else "",
                        "oauth_url": oauth_val if oauth_val is not None else "",
                        "active_tools": [tool["name"] for tool in server_data.get("tools", []) if tool.get("active")]

                    }
                    try:
                        key_name = f"MCP_{url_to_name(url)}"
                        self.set_cached_password(key_name,cred_info)
                    except Exception as e:
                        print(f"Failed to save MCP credentials for {url}: {e}")
                # Update the server list UI
                refresh_server_list()
            except Exception as e:
                messagebox.showerror("Error", str(e))
            finally:
                # Re-enable controls for adding servers
                add_btn.config(state='normal')
                url_entry.config(state='normal')
                auth_menu.config(state='normal')
                token_entry.config(state='normal')
                oauth_entry.config(state='normal')
                save_cb.config(state='normal')

        # Set the Add Server button command after defining do_add
        add_btn.config(command=lambda: asyncio.ensure_future(do_add()))

        # Note: The list will include any servers (saved or added this session) 
        # with their connected status. Double-click allows opening tools for connected 
        # servers or retrying connection for disconnected ones.
    def on_close(self):
        self.loop.stop()
        self.destroy()


def main():
    agent = Agent()
    app = AsyncTk(agent)
    app.mainloop()
    

if __name__ == "__main__":
    main()
