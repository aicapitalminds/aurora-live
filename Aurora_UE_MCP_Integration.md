# Aurora — UE 5.8 MCP Integration (working reference)

Status: CONNECTED and verified (Cowork can read/edit the Face AnimBP live).

## How the connection works
- UE 5.8 runs Epic's official ModelContextProtocol plugin -> HTTP MCP server on `127.0.0.1:8000/mcp`.
- The server does NOT run by itself. It only listens after you start it (see Startup below) or if Auto Start Server is enabled.
- Claude desktop needs HTTPS, so a Cloudflare quick tunnel fronts it. USE 127.0.0.1, NOT localhost:
  `cloudflared tunnel --url http://127.0.0.1:8000`  (leave window open)
  Why: on Windows `localhost` resolves to IPv6 `::1` first, but the UE server binds IPv4 only. A localhost tunnel dials `[::1]:8000` and gets "connection refused" even when the server is up.
- Add the printed `https://<random>.trycloudflare.com/mcp` as a custom Streamable HTTP connector named `unreal`, auth none.
- NOTE: the trycloudflare URL changes every restart -> re-paste into the connector each time.
- When done: Ctrl+C the tunnel window to close the public door.

## Startup (do this each session, in order)
1. In the UE editor, open the console (backtick ` key, or the command box at the bottom) and run:
     `ModelContextProtocol.StartServer 8000`
2. Verify it's listening (PowerShell): `netstat -ano | findstr :8000`
     -> expect a line `127.0.0.1:8000 ... LISTENING`. Empty output = server not started.
3. Start the tunnel: `cloudflared tunnel --url http://127.0.0.1:8000`
4. Copy the new `https://<random>.trycloudflare.com/mcp` into the `unreal` connector.

To skip step 1 every time: Edit -> Editor Preferences -> General -> Model Context Protocol -> enable Auto Start Server. (Port/URL path also live in this panel; defaults 8000 and /mcp.)

## Troubleshooting: "Unable to reach the origin service / connection refused"
- Error shows `dial tcp [::1]:8000` -> IPv6 mismatch. Fix: run the tunnel against 127.0.0.1 (see above).
- `netstat` shows nothing on :8000 -> server isn't started. Run `ModelContextProtocol.StartServer 8000` in the UE console.
- Server IS listening (netstat confirms) but connector still fails right after connecting -> known UE 5.8 experimental bug where the MCP server instantly drops connections. Ref: https://forums.unrealengine.com/t/5-8-experimental-modelcontextprotocol-mcp-server-instantly-drops-connections/2729488

## MCP shape
Server exposes 3 meta-tools: list_toolsets, describe_toolset, call_tool.
Real tools are reached via call_tool(toolset_name, tool_name, arguments).
~54 toolsets. The one we use most:
  editor_toolset.toolsets.blueprint.BlueprintTools

### Reference object shapes (important)
- Asset/Blueprint ref:  {"refPath": "/Game/.../Asset.Asset"}
- Graph ref:            {"refPath": "/Game/.../Asset.Asset:GraphName"}
- Node ref:             {"refPath": "...:NodeGuidOrPath"}
- Pin:                  {"direction": "EGPD_Input"|"EGPD_Output", "index_id": <int>, "node": {"refPath": "..."}}
- pos:                  {"x": <int>, "y": <int>}

### Key BlueprintTools (call via call_tool)
- list_graphs(blueprint)              -> list graph ref