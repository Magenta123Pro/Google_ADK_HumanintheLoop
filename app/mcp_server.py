import asyncio
import json
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

server = Server("hormone-kb")

# The database of correct activities for hormones
HORMONE_DATA = {
    "Estrogen": "Strength training or eating cruciferous vegetables",
    "Progesterone": "Breathwork/meditation, zinc, or limiting alcohol",
    "Insulin": "Fiber-first eating, post-meal walk, or 12-hour rest",
    "Cortisol": "Caffeine elimination after noon, nature immersion, or stretching",
    "LH_FSH": "Adequate calories, consistent sleep, or acupuncture",
    "Melatonin": "Morning sunlight exposure, blue-light block, or magnesium"
}

@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="get_hormone_guidelines",
            description="Retrieve correct target activities for perimenopausal hormones.",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        )
    ]

@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    if name == "get_hormone_guidelines":
        return [
            TextContent(
                type="text",
                text=json.dumps(HORMONE_DATA)
            )
        ]
    raise ValueError(f"Unknown tool: {name}")

async def main():
    async with stdio_server() as (read, write):
        init_options = server.create_initialization_options()
        await server.run(read, write, init_options)

if __name__ == "__main__":
    asyncio.run(main())
