import anyio
from claude_agent_sdk import query, ResultMessage, ClaudeAgentOptions

options = ClaudeAgentOptions(
    output_format={"type": "object", "properties":[{"is_finish":{"type": "bool"}}]}
)

async def main():
    async for message in query(prompt='判断现在的整理进度是否已经完成前十章的整理，只需输出 json', options=options):
        if isinstance(message, ResultMessage) and message.stop_reason =="end_turn":
            print(message.result)

anyio.run(main)