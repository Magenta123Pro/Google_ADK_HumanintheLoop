import asyncio
import json
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

server = Server("hormone-kb")

# The database of correct activities for hormones
HORMONE_DATA = {
    "Estrogen": "Strength training, Eating cruciferous vegetables, or Daily hydration",
    "Progesterone": "Breathwork and meditation, Consuming zinc, or Limiting alcohol intake",
    "Insulin": "Fiber-first eating, Walking post-meals, or Time-restricted feeding",
    "Cortisol": "Caffeine elimination after noon, Nature immersion, or Stretching or Restorative Yoga",
    "LH_FSH": "Adequate caloric intake, Consistent sleep schedule, or Acupuncture",
    "Melatonin": "Morning sunlight, Blue-light blocking, or Magnesium glycinate"
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
